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
            "ce.scan_string",
            "ce.scan_value",
            "ce.scan_once",
            "ce.structure_list",
            "ce.structure_get",
            "ce.structure_create",
            "ce.structure_define",
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


if __name__ == "__main__":
    unittest.main()
