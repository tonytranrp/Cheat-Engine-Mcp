#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_SRC = REPO_ROOT / "python" / "src"
TESTS_DIR = REPO_ROOT / "tests"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from live_support import run_live_tool_suite


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the live Cheat Engine MCP tool suite.")
    parser.add_argument(
        "--process-name",
        default=None,
        help="Primary target process name for live attach checks. Defaults to CE_MCP_PRIMARY_PROCESS or Minecraft.Windows.exe.",
    )
    args = parser.parse_args()

    summary = run_live_tool_suite(primary_process_name=args.process_name)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
