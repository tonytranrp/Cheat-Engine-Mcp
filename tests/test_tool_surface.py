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

from ce_mcp_server.tools import register_all, scan_helper_tools, script_tools
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

    def test_lua_exec_accepts_timeout_override(self) -> None:
        server = FakeServer()
        context = FakeToolContext()
        script_tools.register(server, context)

        result = server.tools["ce.lua_exec"](script="return 1", timeout_seconds=90.0, session_id="ce-test")

        self.assertTrue(result["ok"])
        self.assertEqual(context.script_calls[-1][0], "lua_exec")
        self.assertEqual(context.script_calls[-1][-1], 90.0)

    def test_scan_string_case_sensitive_module_uses_exact_aob_fast_path(self) -> None:
        server = FakeServer()
        context = FakeToolContext()
        scan_helper_tools.register(server, context)

        result = server.tools["ce.scan_string"](
            text="inventory",
            encoding="ascii",
            case_sensitive=True,
            module_name="game.exe",
            timeout_seconds=90.0,
            session_id="ce-test",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["strategy"], "native_exact_aob")
        self.assertEqual(result["returned_count"], 1)
        self.assertEqual(context.native_calls[-1][0], "ce.aob_scan")
        self.assertEqual(context.native_calls[-1][-1], 90.0)

    def test_aob_scan_supports_libhat_scope_controls(self) -> None:
        result = self.server.tools["ce.aob_scan"](
            pattern="48 8B ?? ?? FF",
            module_name="game.exe",
            section_name=".text",
            scan_alignment="x16",
            scan_hint="x86_64|pair0",
            timeout_seconds=45.0,
            session_id="ce-test",
        )

        self.assertTrue(result["ok"])
        tool_name, payload, _, timeout_seconds = self.context.native_calls[-1]
        self.assertEqual(tool_name, "ce.aob_scan")
        self.assertEqual(payload["module_name"], "game.exe")
        self.assertEqual(payload["section_name"], ".text")
        self.assertEqual(payload["scan_alignment"], "x16")
        self.assertEqual(payload["scan_hint"], "x86_64|pair0")
        self.assertEqual(timeout_seconds, 45.0)

    def test_aob_scan_module_unique_uses_native_libhat_scan(self) -> None:
        result = self.server.tools["ce.aob_scan_module_unique"](
            module_name="game.exe",
            pattern="48 8B ?? ?? FF",
            section_name=".rdata",
            scan_alignment="x16",
            scan_hint="pair0",
            timeout_seconds=75.0,
            session_id="ce-test",
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["unique"])
        self.assertEqual(result["address"], 0x140000200)
        tool_name, payload, _, timeout_seconds = self.context.native_calls[-1]
        self.assertEqual(tool_name, "ce.aob_scan")
        self.assertEqual(payload["module_name"], "game.exe")
        self.assertEqual(payload["section_name"], ".rdata")
        self.assertEqual(payload["scan_alignment"], "x16")
        self.assertEqual(payload["scan_hint"], "pair0")
        self.assertEqual(payload["max_results"], 2)
        self.assertEqual(timeout_seconds, 75.0)


if __name__ == "__main__":
    unittest.main()
