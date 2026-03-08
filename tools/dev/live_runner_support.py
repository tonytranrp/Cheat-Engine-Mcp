from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def get_process_command_line(pid: int) -> str | None:
    command = (
        "Get-CimInstance Win32_Process "
        f"-Filter \"ProcessId = {pid}\" | "
        "Select-Object -ExpandProperty CommandLine"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    return text or None


def looks_like_stdio_backend(command_line: str | None) -> bool:
    if not command_line:
        return False
    normalized = command_line.casefold()
    if "ce_mcp_server" not in normalized:
        return False
    if "--transport" not in normalized:
        return True
    return "--transport stdio" in normalized


def is_port_listening(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def find_listening_pid(port: int) -> int | None:
    result = subprocess.run(
        ["netstat", "-ano", "-p", "TCP"],
        capture_output=True,
        text=True,
        check=True,
    )
    listen_targets = {f"127.0.0.1:{port}", f"0.0.0.0:{port}", f"[::]:{port}"}
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line.startswith("TCP"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        if parts[1] not in listen_targets:
            continue
        if parts[3].upper() != "LISTENING":
            continue
        try:
            return int(parts[4])
        except ValueError:
            return None
    return None


def stop_process(pid: int) -> None:
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/F"],
        capture_output=True,
        text=True,
        check=True,
    )


def start_backend(repo_root: Path) -> subprocess.Popen[str]:
    env = os.environ.copy()
    python_src = str(repo_root / "python" / "src")
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = python_src if not existing_pythonpath else python_src + os.pathsep + existing_pythonpath
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        [sys.executable, "-m", "ce_mcp_server", "--transport", "bridge-only"],
        cwd=repo_root,
        env=env,
        creationflags=creationflags,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def wait_for_port_state(port: int, *, should_listen: bool, timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if is_port_listening(port) == should_listen:
            return
        time.sleep(0.25)
    state = "listening" if should_listen else "free"
    raise RuntimeError(f"port {port} did not become {state} within {timeout_seconds:.1f}s")


def wait_for_backend_start(process: subprocess.Popen[str], port: int, timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if is_port_listening(port):
            return
        if process.poll() is not None:
            stdout = process.stdout.read() if process.stdout is not None else ""
            stderr = process.stderr.read() if process.stderr is not None else ""
            raise RuntimeError(
                "ce_mcp_server exited before binding the bridge port.\n"
                f"stdout:\n{stdout}\n"
                f"stderr:\n{stderr}"
            )
        time.sleep(0.25)
    raise RuntimeError(f"ce_mcp_server did not bind port {port} within {timeout_seconds:.1f}s")


@contextmanager
def managed_bridge_backend(repo_root: Path,
                           *,
                           port: int = 5556,
                           manage_existing_backend: bool = False) -> Iterator[None]:
    existing_pid = find_listening_pid(port)
    restarted_backend: subprocess.Popen[str] | None = None

    if existing_pid is not None:
        if not manage_existing_backend:
            raise RuntimeError(
                f"port {port} is already in use by PID {existing_pid}. "
                "Stop the existing ce_mcp_server instance first or rerun with --manage-existing-backend."
            )
        existing_command_line = get_process_command_line(existing_pid)
        if looks_like_stdio_backend(existing_command_line):
            raise RuntimeError(
                f"refusing to stop PID {existing_pid} on port {port} because it appears to be a stdio-backed "
                "ce_mcp_server process. Stopping it would sever the active MCP client transport. "
                "Use a dedicated bridge port and restart Cheat Engine into that port for isolated live validation."
            )
        stop_process(existing_pid)
        wait_for_port_state(port, should_listen=False, timeout_seconds=10.0)

    try:
        yield
    finally:
        if existing_pid is not None and manage_existing_backend:
            wait_for_port_state(port, should_listen=False, timeout_seconds=20.0)
            restarted_backend = start_backend(repo_root)
            wait_for_backend_start(restarted_backend, port, timeout_seconds=20.0)
        if restarted_backend is not None and restarted_backend.poll() is not None:
            raise RuntimeError("failed to restart ce_mcp_server after the live run")
