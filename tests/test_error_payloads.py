from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_SRC = REPO_ROOT / "python" / "src"
TESTS_DIR = REPO_ROOT / "tests"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from ce_mcp_server.tools import debug_tools, scan_helper_tools, scan_tools
from test_support import FakeServer, FakeToolContext


class ScanStateErrorContext(FakeToolContext):
    def call_runtime_function(self, runtime, function_name, args=None, session_id=None, timeout_seconds=30.0):
        runtime_name = getattr(runtime, "name", "runtime")
        if runtime_name == "scan" and function_name == "get_session_state":
            return {
                "ok": True,
                "session_id": "scan-1",
                "state": "created",
                "scan_in_progress": False,
                "has_completed_scan": False,
                "last_scan_kind": None,
                "last_result_count": 0,
            }
        return super().call_runtime_function(runtime, function_name, args=args, session_id=session_id, timeout_seconds=timeout_seconds)


class ScanRuntimeFailureContext(FakeToolContext):
    def call_runtime_function(self, runtime, function_name, args=None, session_id=None, timeout_seconds=30.0):
        runtime_name = getattr(runtime, "name", "runtime")
        if runtime_name == "scan" and function_name == "get_results":
            return {
                "ok": False,
                "error": "scan_sequence_error:wait_required_before_results",
                "session_id": session_id or "ce-test",
            }
        return super().call_runtime_function(runtime, function_name, args=args, session_id=session_id, timeout_seconds=timeout_seconds)


class DebugBreakpointRejectedContext(FakeToolContext):
    def call_runtime_function(self, runtime, function_name, args=None, session_id=None, timeout_seconds=30.0):
        runtime_name = getattr(runtime, "name", "runtime")
        if runtime_name == "debug" and function_name == "watch_start":
            return {
                "ok": False,
                "error": "debug_setBreakpoint_failed",
                "session_id": session_id or "ce-test",
            }
        return super().call_runtime_function(runtime, function_name, args=args, session_id=session_id, timeout_seconds=timeout_seconds)


class DebugStartRejectedContext(FakeToolContext):
    def call_runtime_function(self, runtime, function_name, args=None, session_id=None, timeout_seconds=30.0):
        runtime_name = getattr(runtime, "name", "runtime")
        if runtime_name == "debug" and function_name == "start":
            return {
                "ok": False,
                "error": "debugger_start_failed:1",
                "session_id": session_id or "ce-test",
            }
        return super().call_runtime_function(runtime, function_name, args=args, session_id=session_id, timeout_seconds=timeout_seconds)


class ErrorPayloadTests(unittest.TestCase):
    def test_invalid_scan_string_encoding_returns_guidance(self) -> None:
        server = FakeServer()
        scan_helper_tools.register(server, FakeToolContext())

        result = server.tools["ce.scan_string"](text="inventory", encoding="utf8", session_id="ce-test")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "invalid_scan_encoding")
        self.assertIn("hint", result)
        self.assertIn("example", result)

    def test_scan_next_ex_requires_completed_first_scan(self) -> None:
        server = FakeServer()
        scan_helper_tools.register(server, ScanStateErrorContext())

        result = server.tools["ce.scan_next_ex"](scan_session_id="scan-1", session_id="ce-test")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "scan_first_scan_required")
        self.assertIn("required_order", result)
        self.assertIn("ce.scan_first_ex", " ".join(result["required_order"]))

    def test_runtime_scan_errors_are_annotated(self) -> None:
        server = FakeServer()
        scan_tools.register(server, ScanRuntimeFailureContext())

        result = server.tools["ce.scan_get_results"](scan_session_id="scan-1", limit=10, session_id="ce-test")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "scan_results_wait_required")
        self.assertIn("next_steps", result)

    def test_debug_breakpoint_rejection_returns_guidance(self) -> None:
        server = FakeServer()
        debug_tools.register(server, DebugBreakpointRejectedContext())

        result = server.tools["ce.debug_watch_accesses_start"](address="game.exe+0", session_id="ce-test")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "debug_breakpoint_rejected")
        self.assertIn("required_order", result)

    def test_debug_start_failure_is_annotated_with_interface(self) -> None:
        server = FakeServer()
        debug_tools.register(server, DebugStartRejectedContext())

        result = server.tools["ce.debug_start"](debugger_interface=1, session_id="ce-test")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "debugger_start_failed")
        self.assertEqual(result["details"]["debugger_interface"], "1")


if __name__ == "__main__":
    unittest.main()
