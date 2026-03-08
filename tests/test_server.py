from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_SRC = REPO_ROOT / "python" / "src"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

from ce_mcp_server import server


class DummyBridge:
    def __init__(self) -> None:
        self.host = "127.0.0.1"
        self.port = 5556
        self.started = 0
        self.stopped = 0

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1


class ServerTests(unittest.TestCase):
    def test_run_bridge_only_starts_and_stops_bridge(self) -> None:
        bridge = DummyBridge()

        with patch.object(server.time, "sleep", side_effect=KeyboardInterrupt):
            server.run_bridge_only(bridge)

        self.assertEqual(bridge.started, 1)
        self.assertEqual(bridge.stopped, 1)


if __name__ == "__main__":
    unittest.main()
