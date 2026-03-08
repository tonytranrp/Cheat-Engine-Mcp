from __future__ import annotations

import json
import logging
import socket
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


class BridgeError(RuntimeError):
    pass


class NoSessionError(BridgeError):
    pass


class SessionDisconnectedError(BridgeError):
    pass


class ToolTimeoutError(BridgeError):
    pass


@dataclass(slots=True)
class PendingCall:
    event: threading.Event = field(default_factory=threading.Event)
    response: dict[str, Any] | None = None


@dataclass(slots=True)
class SessionInfo:
    session_id: str
    peer: str
    connected_at: float
    plugin: str
    plugin_id: int | None
    sdk_version: int | None
    ce_process_id: int | None
    tools: list[str]


class CheatEngineSession:
    def __init__(self,
                 sock: socket.socket,
                 reader,
                 writer,
                 info: SessionInfo,
                 on_close,
                 logger: logging.Logger) -> None:
        self._sock = sock
        self._reader = reader
        self._writer = writer
        self._info = info
        self._on_close = on_close
        self._logger = logger
        self._send_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending: dict[str, PendingCall] = {}
        self._closed = threading.Event()
        self._reader_thread = threading.Thread(target=self._reader_loop,
                                               name=f"ce-bridge-{info.session_id}",
                                               daemon=True)

    @classmethod
    def accept(cls,
               sock: socket.socket,
               peer: tuple[str, int],
               on_close,
               logger: logging.Logger) -> "CheatEngineSession":
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        reader = sock.makefile("r", encoding="utf-8", newline="\n")
        writer = sock.makefile("w", encoding="utf-8", newline="\n")

        hello_line = reader.readline()
        if not hello_line:
            raise BridgeError("bridge client disconnected before hello")

        hello = json.loads(hello_line)
        if hello.get("type") != "hello":
            raise BridgeError(f"unexpected initial message: {hello!r}")

        ce_process_id = hello.get("ce_process_id")
        if isinstance(ce_process_id, int):
            session_id = f"ce-{ce_process_id}"
        else:
            session_id = f"ce-{uuid.uuid4().hex[:8]}"

        info = SessionInfo(
            session_id=session_id,
            peer=f"{peer[0]}:{peer[1]}",
            connected_at=time.time(),
            plugin=str(hello.get("plugin", "unknown")),
            plugin_id=hello.get("plugin_id") if isinstance(hello.get("plugin_id"), int) else None,
            sdk_version=hello.get("sdk_version") if isinstance(hello.get("sdk_version"), int) else None,
            ce_process_id=ce_process_id if isinstance(ce_process_id, int) else None,
            tools=[tool for tool in hello.get("tools", []) if isinstance(tool, str)],
        )

        session = cls(sock=sock, reader=reader, writer=writer, info=info, on_close=on_close, logger=logger)
        session._send_message({"type": "welcome"})
        session._reader_thread.start()
        return session

    @property
    def info(self) -> SessionInfo:
        return self._info

    def is_closed(self) -> bool:
        return self._closed.is_set()

    def close(self) -> None:
        if self._closed.is_set():
            return

        self._closed.set()
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

        try:
            self._reader.close()
        except OSError:
            pass

        try:
            self._writer.close()
        except OSError:
            pass

        try:
            self._sock.close()
        except OSError:
            pass

        with self._pending_lock:
            pending = list(self._pending.values())
            self._pending.clear()

        for item in pending:
            item.event.set()

        self._on_close(self._info.session_id)

    def call_tool(self, tool_name: str, payload: dict[str, Any] | None = None, timeout_seconds: float = 10.0) -> dict[str, Any]:
        if self._closed.is_set():
            raise SessionDisconnectedError(f"session '{self._info.session_id}' is disconnected")

        request_id = uuid.uuid4().hex
        pending = PendingCall()
        with self._pending_lock:
            self._pending[request_id] = pending

        try:
            message = {"type": "call", "id": request_id, "tool": tool_name}
            if payload:
                message.update(payload)
            self._send_message(message)

            if not pending.event.wait(timeout_seconds):
                raise ToolTimeoutError(f"tool '{tool_name}' timed out after {timeout_seconds:.1f}s")

            if pending.response is None:
                raise SessionDisconnectedError(f"session '{self._info.session_id}' disconnected while waiting for '{tool_name}'")

            return pending.response
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)

    def _send_message(self, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, separators=(",", ":"))
        with self._send_lock:
            self._writer.write(line)
            self._writer.write("\n")
            self._writer.flush()

    def _reader_loop(self) -> None:
        try:
            while not self._closed.is_set():
                line = self._reader.readline()
                if not line:
                    return

                message = json.loads(line)
                self._handle_message(message)
        except (OSError, ValueError) as exc:
            self._logger.info("CE session %s closed: %s", self._info.session_id, exc)
        finally:
            self.close()

    def _handle_message(self, message: dict[str, Any]) -> None:
        message_type = message.get("type")
        if message_type == "result":
            request_id = message.get("id")
            if not isinstance(request_id, str):
                return

            with self._pending_lock:
                pending = self._pending.get(request_id)

            if pending is None:
                return

            pending.response = message
            pending.event.set()
            return

        if message_type == "ping":
            self._send_message({"type": "pong"})
            return

        self._logger.debug("Ignoring bridge message from %s: %s", self._info.session_id, message)


class CheatEngineBridge:
    def __init__(self, host: str = "127.0.0.1", port: int = 5556, logger: logging.Logger | None = None) -> None:
        self._host = host
        self._port = port
        self._logger = logger or logging.getLogger("ce-mcp.bridge")
        self._listener: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._sessions: dict[str, CheatEngineSession] = {}

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> None:
        if self._listener is not None:
            return

        self._stop_event.clear()
        listener = socket.create_server((self._host, self._port), reuse_port=False)
        listener.settimeout(1.0)
        self._listener = listener
        self._accept_thread = threading.Thread(target=self._accept_loop, name="ce-bridge-accept", daemon=True)
        self._accept_thread.start()
        self._logger.info("Listening for Cheat Engine bridge clients on %s:%d", self._host, self._port)

    def stop(self) -> None:
        self._stop_event.set()
        listener = self._listener
        self._listener = None
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass

        if self._accept_thread is not None:
            self._accept_thread.join(timeout=2.0)
            self._accept_thread = None

        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()

        for session in sessions:
            session.close()

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            sessions = [asdict(session.info) for session in self._sessions.values()]

        sessions.sort(key=lambda item: item["connected_at"], reverse=True)
        return sessions

    def status(self) -> dict[str, Any]:
        return {
            "host": self._host,
            "port": self._port,
            "session_count": len(self.list_sessions()),
            "sessions": self.list_sessions(),
        }

    def call_tool(self,
                  tool_name: str,
                  payload: dict[str, Any] | None = None,
                  session_id: str | None = None,
                  timeout_seconds: float = 10.0) -> dict[str, Any]:
        session, redirected_from = self._resolve_session(session_id)
        response = session.call_tool(tool_name, payload=payload, timeout_seconds=timeout_seconds)
        result: dict[str, Any]
        if response.get("ok") is True:
            result = self._normalize_result_payload(response.get("result"))
            result.setdefault("ok", True)
        else:
            result = {"ok": False, "error": response.get("error", "bridge_call_failed")}
            if "win32_error" in response:
                result["win32_error"] = response["win32_error"]

        result.setdefault("session_id", session.info.session_id)
        result["bridge_session_id"] = session.info.session_id
        if redirected_from is not None and redirected_from != session.info.session_id:
            result["requested_session_id"] = redirected_from
            result["session_redirected"] = True
            result["session_redirect_reason"] = (
                f"requested session '{redirected_from}' was not connected; "
                f"using the only live session '{session.info.session_id}'"
            )
        if session.info.ce_process_id is not None:
            result["ce_process_id"] = session.info.ce_process_id
        return result

    @staticmethod
    def _normalize_result_payload(payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            return dict(payload)
        if isinstance(payload, list):
            return {"items": list(payload)}
        return {"value": payload}

    def _accept_loop(self) -> None:
        assert self._listener is not None
        while not self._stop_event.is_set():
            try:
                sock, peer = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                if self._stop_event.is_set():
                    return
                raise

            try:
                session = CheatEngineSession.accept(sock=sock, peer=peer, on_close=self._drop_session, logger=self._logger)
            except Exception as exc:
                self._logger.warning("Failed to accept CE bridge client from %s:%d: %s", peer[0], peer[1], exc)
                try:
                    sock.close()
                except OSError:
                    pass
                continue

            with self._lock:
                previous = self._sessions.get(session.info.session_id)
                self._sessions[session.info.session_id] = session

            if previous is not None and previous is not session:
                previous.close()

            self._logger.info("CE session connected: %s", session.info.session_id)

    def _drop_session(self, session_id: str) -> None:
        with self._lock:
            current = self._sessions.get(session_id)
            if current is not None and current.is_closed():
                self._sessions.pop(session_id, None)

    def resolve_session_id(self, session_id: str | None = None) -> str:
        session, _ = self._resolve_session(session_id)
        return session.info.session_id

    def _resolve_session(self, session_id: str | None) -> tuple[CheatEngineSession, str | None]:
        with self._lock:
            if session_id is not None:
                session = self._sessions.get(session_id)
                if session is not None:
                    return session, None

                if len(self._sessions) == 1:
                    return next(iter(self._sessions.values())), session_id

                raise NoSessionError(f"session '{session_id}' is not connected")

            if not self._sessions:
                raise NoSessionError("no Cheat Engine session is connected")

            if len(self._sessions) == 1:
                return next(iter(self._sessions.values())), None

            connected = sorted(self._sessions.values(), key=lambda item: item.info.connected_at, reverse=True)
            return connected[0], None
