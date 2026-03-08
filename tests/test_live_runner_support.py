from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DEV = REPO_ROOT / "tools" / "dev"
if str(TOOLS_DEV) not in sys.path:
    sys.path.insert(0, str(TOOLS_DEV))

import live_runner_support


class DummyPopen:
    def __init__(self, args, kwargs) -> None:
        self.args = args
        self.kwargs = kwargs


class LiveRunnerSupportTests(unittest.TestCase):
    def test_looks_like_stdio_backend_matches_default_server_command(self) -> None:
        self.assertTrue(live_runner_support.looks_like_stdio_backend("python -m ce_mcp_server"))
        self.assertTrue(live_runner_support.looks_like_stdio_backend("python -m ce_mcp_server --transport stdio"))
        self.assertFalse(live_runner_support.looks_like_stdio_backend("python -m ce_mcp_server --transport bridge-only"))

    def test_start_backend_uses_bridge_only_transport(self) -> None:
        captured: dict[str, object] = {}

        def fake_popen(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return DummyPopen(args, kwargs)

        with patch.object(live_runner_support.subprocess, "Popen", side_effect=fake_popen):
            process = live_runner_support.start_backend(REPO_ROOT)

        self.assertIsInstance(process, DummyPopen)
        command = list(captured["args"][0])
        self.assertEqual(command[:3], [sys.executable, "-m", "ce_mcp_server"])
        self.assertEqual(command[3:], ["--transport", "bridge-only"])

        kwargs = dict(captured["kwargs"])
        env = dict(kwargs["env"])
        self.assertIn(str(REPO_ROOT / "python" / "src"), env["PYTHONPATH"])
        self.assertEqual(kwargs["cwd"], REPO_ROOT)


if __name__ == "__main__":
    unittest.main()
