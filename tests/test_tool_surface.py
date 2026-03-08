from __future__ import annotations

import inspect
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

from ce_mcp_server.tools import register_all
from test_support import FakeServer, FakeToolContext, build_sample_args


class ToolSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = FakeServer()
        cls.context = FakeToolContext()
        register_all(cls.server, cls.context)

    def test_tool_count_floor(self) -> None:
        self.assertGreaterEqual(len(self.server.tools), 170)

    def test_expected_new_tools_exist(self) -> None:
        expected = {
            "ce.normalize_address",
            "ce.verify_target",
            "ce.scan_string",
            "ce.scan_value",
            "ce.scan_once",
            "ce.lua_get_environment",
            "ce.lua_configure_environment",
            "ce.lua_remove_library_root",
            "ce.lua_reset_environment",
            "ce.lua_preload_module",
            "ce.lua_preload_file",
            "ce.lua_eval_with_globals",
            "ce.lua_exec_with_globals",
            "ce.structure_list",
            "ce.structure_get",
            "ce.structure_create",
            "ce.structure_define",
            "ce.structure_read",
            "ce.record_create_many",
            "ce.record_create_group",
            "ce.dissect_module",
            "ce.dissect_get_references",
            "ce.debug_status",
            "ce.debug_watch_accesses_start",
            "ce.debug_watch_get_hits",
        }
        self.assertTrue(expected.issubset(set(self.server.tools)))

    def test_every_registered_tool_invokes(self) -> None:
        failures: list[str] = []
        for tool_name, function in sorted(self.server.tools.items()):
            try:
                args = build_sample_args(tool_name, inspect.signature(function))
                result = function(**args)
                self.assertIsInstance(result, dict, msg=tool_name)
                self.assertNotIn("error", result, msg=f"{tool_name}: {result}")
            except Exception as exc:  # pragma: no cover - test should fail with useful aggregation
                failures.append(f"{tool_name}: {exc}")

        if failures:
            self.fail("Tool invocation failures:\n" + "\n".join(failures))

    def test_normalize_address_resolves_expression(self) -> None:
        result = self.server.tools["ce.normalize_address"](address="game.exe+0", session_id="ce-test")
        self.assertEqual(result["address"], 0x140000000)
        self.assertEqual(result["address_hex"], hex(0x140000000))
        self.assertEqual(result["resolved_via"], "ce_expression")
        self.assertEqual(result["symbol"], "game.exe+0")

    def test_verify_target_reports_main_module(self) -> None:
        result = self.server.tools["ce.verify_target"](session_id="ce-test")
        self.assertTrue(result["ready"])
        self.assertTrue(result["attached"])
        self.assertEqual(result["process_name"], "game.exe")
        self.assertEqual(result["main_module"]["module_name"], "game.exe")

    def test_structure_read_returns_named_fields(self) -> None:
        result = self.server.tools["ce.structure_read"](name="Player", index=None, address="game.exe+0", max_depth=1, include_raw=True, session_id="ce-test")
        self.assertEqual(result["structure"]["name"], "Player")
        self.assertEqual(result["fields"][0]["name"], "health")

    def test_lua_eval_with_globals_wraps_temp_globals(self) -> None:
        result = self.server.tools["ce.lua_eval_with_globals"](script="player_name", globals={"player_name": "Alex"}, session_id="ce-test")
        self.assertIn("player_name", result["value"])

    def test_lua_reset_environment_exists(self) -> None:
        result = self.server.tools["ce.lua_reset_environment"](session_id="ce-test")
        self.assertTrue(result["reset"])


if __name__ == "__main__":
    unittest.main()
