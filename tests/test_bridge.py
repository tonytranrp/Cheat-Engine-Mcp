from __future__ import annotations

import logging
import socket
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_SRC = REPO_ROOT / "python" / "src"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

from ce_mcp_server.bridge import CheatEngineBridge
from ce_mcp_server.bridge import CheatEngineSession, NoSessionError, SessionInfo, ToolTimeoutError


class DummySession:
    def __init__(self, session_id: str, *, connected_at: float = 1.0) -> None:
        self.info = SessionInfo(
            session_id=session_id,
            peer="127.0.0.1:5556",
            connected_at=connected_at,
            plugin="MCP Bridge Plugin",
            plugin_id=1,
            sdk_version=6,
            ce_process_id=1234,
            tools=[],
        )

    def call_tool(self, tool_name: str, payload=None, timeout_seconds: float = 10.0):
        return {"ok": True, "result": {"tool_name": tool_name, "timeout_seconds": timeout_seconds}}

    def is_closed(self) -> bool:
        return False


class BridgeTests(unittest.TestCase):
    def test_normalize_result_payload_handles_mapping(self) -> None:
        self.assertEqual(CheatEngineBridge._normalize_result_payload({"x": 1}), {"x": 1})

    def test_normalize_result_payload_handles_list(self) -> None:
        self.assertEqual(CheatEngineBridge._normalize_result_payload([1, 2]), {"items": [1, 2]})

    def test_normalize_result_payload_handles_scalar(self) -> None:
        self.assertEqual(CheatEngineBridge._normalize_result_payload(7), {"value": 7})

    def test_explicit_stale_session_redirects_to_only_live_session(self) -> None:
        bridge = CheatEngineBridge()
        bridge._sessions = {"ce-live": DummySession("ce-live")}

        result = bridge.call_tool("ce.read_memory", session_id="ce-stale")

        self.assertTrue(result["ok"])
        self.assertEqual(result["session_id"], "ce-live")
        self.assertEqual(result["requested_session_id"], "ce-stale")
        self.assertTrue(result["session_redirected"])

    def test_stale_session_with_multiple_live_sessions_still_errors(self) -> None:
        bridge = CheatEngineBridge()
        bridge._sessions = {
            "ce-a": DummySession("ce-a", connected_at=1.0),
            "ce-b": DummySession("ce-b", connected_at=2.0),
        }

        with self.assertRaises(NoSessionError):
            bridge.call_tool("ce.read_memory", session_id="ce-stale")

    def test_timed_out_session_closes_itself(self) -> None:
        left, right = socket.socketpair()
        try:
            closed_sessions: list[str] = []
            reader = left.makefile("r", encoding="utf-8", newline="\n")
            writer = left.makefile("w", encoding="utf-8", newline="\n")
            session = CheatEngineSession(
                sock=left,
                reader=reader,
                writer=writer,
                info=SessionInfo(
                    session_id="ce-timeout",
                    peer="127.0.0.1:5556",
                    connected_at=1.0,
                    plugin="MCP Bridge Plugin",
                    plugin_id=1,
                    sdk_version=6,
                    ce_process_id=1234,
                    tools=[],
                ),
                on_close=closed_sessions.append,
                logger=logging.getLogger("ce_mcp.tests.bridge"),
            )

            with self.assertRaises(ToolTimeoutError):
                session.call_tool("ce.read_memory", timeout_seconds=0.01)

            self.assertTrue(session.is_closed())
            self.assertEqual(closed_sessions, ["ce-timeout"])
        finally:
            right.close()


if __name__ == "__main__":
    unittest.main()
