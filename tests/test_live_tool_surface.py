from __future__ import annotations

import os
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

from live_support import run_live_tool_suite


@unittest.skipUnless(os.environ.get("CE_MCP_RUN_LIVE") == "1", "set CE_MCP_RUN_LIVE=1 to run live Cheat Engine integration tests")
class LiveToolSurfaceTests(unittest.TestCase):
    def test_every_registered_tool_invokes_live(self) -> None:
        summary = run_live_tool_suite()
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["tool_count"], summary["invoked_count"])


if __name__ == "__main__":
    unittest.main()
