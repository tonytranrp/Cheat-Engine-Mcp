from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_SRC = REPO_ROOT / "python" / "src"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

from ce_mcp_server.bridge import CheatEngineBridge


class BridgeTests(unittest.TestCase):
    def test_normalize_result_payload_handles_mapping(self) -> None:
        self.assertEqual(CheatEngineBridge._normalize_result_payload({"x": 1}), {"x": 1})

    def test_normalize_result_payload_handles_list(self) -> None:
        self.assertEqual(CheatEngineBridge._normalize_result_payload([1, 2]), {"items": [1, 2]})

    def test_normalize_result_payload_handles_scalar(self) -> None:
        self.assertEqual(CheatEngineBridge._normalize_result_payload(7), {"value": 7})


if __name__ == "__main__":
    unittest.main()
