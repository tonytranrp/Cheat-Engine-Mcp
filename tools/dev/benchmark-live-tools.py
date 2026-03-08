#!/usr/bin/env python3
from __future__ import annotations

import argparse
import inspect
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_SRC = REPO_ROOT / "python" / "src"
TESTS_DIR = REPO_ROOT / "tests"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from live_runner_support import managed_bridge_backend
from live_support import LiveToolSuite


def summarize_samples(samples: list[float]) -> dict[str, float | int]:
    ordered = sorted(samples)
    count = len(ordered)
    p95_index = min(count - 1, max(0, int(count * 0.95) - 1))
    return {
        "count": count,
        "min_ms": round(ordered[0], 3),
        "avg_ms": round(statistics.fmean(ordered), 3),
        "p50_ms": round(ordered[(count - 1) // 2], 3),
        "p95_ms": round(ordered[p95_index], 3),
        "max_ms": round(ordered[-1], 3),
        "total_ms": round(sum(ordered), 3),
    }


def benchmark_iterations(label: str, iterations: int, action: Callable[[], Any]) -> dict[str, Any]:
    samples: list[float] = []
    for _ in range(iterations):
        started_at = time.perf_counter()
        action()
        samples.append((time.perf_counter() - started_at) * 1000.0)
    result = summarize_samples(samples)
    result["label"] = label
    return result


def benchmark_parallel(label: str,
                       total_calls: int,
                       workers: int,
                       action_factory: Callable[[int], Callable[[], Any]]) -> dict[str, Any]:
    def run_one(index: int) -> float:
        action = action_factory(index)
        started_at = time.perf_counter()
        action()
        return (time.perf_counter() - started_at) * 1000.0

    started_at = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        samples = list(executor.map(run_one, range(total_calls)))
    wall_ms = (time.perf_counter() - started_at) * 1000.0

    result = summarize_samples(samples)
    result["label"] = label
    result["workers"] = workers
    result["wall_ms"] = round(wall_ms, 3)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark common live Cheat Engine MCP workflows.")
    parser.add_argument("--process-name", default="Minecraft.Windows.exe")
    parser.add_argument("--port", type=int, default=5556)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--scan-iterations", type=int, default=3)
    parser.add_argument("--parallel-calls", type=int, default=16)
    parser.add_argument("--parallel-workers", type=int, default=4)
    parser.add_argument(
        "--manage-existing-backend",
        action="store_true",
        help="Temporarily stop and restore an existing detached bridge listener on this port. Refuses stdio-backed ce_mcp_server instances.",
    )
    args = parser.parse_args()

    with managed_bridge_backend(REPO_ROOT, port=args.port, manage_existing_backend=args.manage_existing_backend):
        suite = LiveToolSuite(port=args.port, primary_process_name=args.process_name)
        suite.start()
        try:
            assert suite.remote_scratch is not None
            assert suite.primary_module_name is not None

            bench_structure_name = "CE_MCP_Benchmark_Structure"
            suite._call(
                "ce.structure_define",
                name=bench_structure_name,
                elements=[
                    {"offset": 0, "name": "health", "vartype": "dword", "bytesize": 4},
                    {"offset": 4, "name": "speed", "vartype": "float", "bytesize": 4},
                ],
                add_global=True,
            )
            suite.structure_names.append(bench_structure_name)
            suite._call(
                "ce.lua_exec",
                script=(
                    f"writeInteger({suite.remote_scratch.base + 0xA00}, 321)\n"
                    f"writeFloat({suite.remote_scratch.base + 0xA04}, 1.5)\n"
                    "return { ok = true }"
                ),
            )

            def call(tool_name: str, **kwargs: Any) -> dict[str, Any]:
                function = suite.server.tools[tool_name]
                signature = inspect.signature(function)
                if "session_id" in signature.parameters and "session_id" not in kwargs and suite.session_id is not None:
                    kwargs["session_id"] = suite.session_id
                result = function(**kwargs)
                if isinstance(result, dict) and result.get("ok") is False:
                    raise RuntimeError(f"{tool_name} failed: {json.dumps(result)}")
                return result

            benchmarks = [
                benchmark_iterations(
                    "ce.attach_process(same target)",
                    args.iterations,
                    lambda: call("ce.attach_process", process_name=args.process_name),
                ),
                benchmark_iterations("ce.verify_target", args.iterations, lambda: call("ce.verify_target")),
                benchmark_iterations(
                    "ce.normalize_address",
                    args.iterations,
                    lambda: call("ce.normalize_address", address=f"{suite.primary_module_name}+0"),
                ),
                benchmark_iterations(
                    "ce.read_integer",
                    args.iterations,
                    lambda: call("ce.read_integer", address=suite.remote_scratch.integer_address),
                ),
                benchmark_iterations(
                    "ce.read_bytes_table",
                    args.iterations,
                    lambda: call("ce.read_bytes_table", address=suite.remote_scratch.bytes_address, count=4),
                ),
                benchmark_iterations("ce.lua_eval", args.iterations, lambda: call("ce.lua_eval", script="1+1")),
                benchmark_iterations(
                    "ce.lua_call(readInteger)",
                    args.iterations,
                    lambda: call("ce.lua_call", function_name="readInteger", args=[suite.remote_scratch.integer_address], result_field="value"),
                ),
                benchmark_iterations(
                    "ce.lua_eval_with_globals",
                    args.iterations,
                    lambda: call("ce.lua_eval_with_globals", script="alpha + beta", globals={"alpha": 7, "beta": 35}),
                ),
                benchmark_iterations(
                    "ce.structure_read",
                    args.iterations,
                    lambda: call("ce.structure_read", name=bench_structure_name, address=suite.remote_scratch.base + 0xA00, max_depth=1, include_raw=False),
                ),
                benchmark_iterations(
                    "ce.scan_once",
                    args.scan_iterations,
                    lambda: call(
                        "ce.scan_once",
                        scan_option="exact",
                        value_type="dword",
                        value=0x51525354,
                        start_address=suite.remote_scratch.base,
                        end_address=suite.remote_scratch.base + suite.remote_scratch.size,
                    ),
                ),
                benchmark_iterations(
                    "ce.aob_scan(range,x16)",
                    args.iterations,
                    lambda: call(
                        "ce.aob_scan",
                        pattern=suite.remote_scratch.pattern_hex,
                        start_address=suite.remote_scratch.pattern_address,
                        end_address=suite.remote_scratch.pattern_address + 0x40,
                        scan_alignment="x16",
                        scan_hint="pair0",
                        max_results=2,
                    ),
                ),
                benchmark_iterations(
                    "ce.aob_scan_unique(range,x16)",
                    args.iterations,
                    lambda: call(
                        "ce.aob_scan_unique",
                        pattern=suite.remote_scratch.pattern_hex,
                        start_address=suite.remote_scratch.pattern_address,
                        end_address=suite.remote_scratch.pattern_address + 0x40,
                        scan_alignment="x16",
                        scan_hint="pair0",
                    ),
                ),
                benchmark_iterations(
                    "ce.scan_string(range,ascii)",
                    args.iterations,
                    lambda: call(
                        "ce.scan_string",
                        text="ce_mcp_inventory_ascii",
                        encoding="ascii",
                        case_sensitive=True,
                        start_address=suite.remote_scratch.base,
                        end_address=suite.remote_scratch.base + suite.remote_scratch.size,
                    ),
                ),
                benchmark_iterations(
                    "ce.aob_scan_module_unique(main module)",
                    args.scan_iterations,
                    lambda: call(
                        "ce.aob_scan_module_unique",
                        module_name=suite.primary_module_name,
                        pattern="4D 5A 90 00 03 00 00 00 04 00 00 00 FF FF 00 00",
                    ),
                ),
                benchmark_parallel(
                    "parallel_mixed_light",
                    args.parallel_calls,
                    args.parallel_workers,
                    lambda index: (
                        (lambda: call("ce.read_integer", address=suite.remote_scratch.integer_address))
                        if index % 3 == 0
                        else (lambda: call("ce.normalize_address", address=f"{suite.primary_module_name}+0"))
                        if index % 3 == 1
                        else (lambda: call("ce.lua_eval", script="1+1"))
                    ),
                ),
            ]

            output = {
                "ok": True,
                "process_name": args.process_name,
                "process_id": suite.primary_process_id,
                "module_name": suite.primary_module_name,
                "module_base": suite.primary_module_base,
                "iterations": args.iterations,
                "scan_iterations": args.scan_iterations,
                "parallel_calls": args.parallel_calls,
                "parallel_workers": args.parallel_workers,
                "benchmarks": benchmarks,
            }
            print(json.dumps(output, indent=2))
            return 0
        finally:
            suite.stop()


if __name__ == "__main__":
    raise SystemExit(main())
