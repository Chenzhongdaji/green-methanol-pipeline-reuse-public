#!/usr/bin/env python3
"""Command-line entry point for the portable aggregate reproduction."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from green_methanol_release.reproduce import run_reproduction


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        report = run_reproduction(args.root, args.mode, args.output)
    except (OSError, ValueError) as exc:
        print(f"error={exc}", file=sys.stderr)
        return 1
    print(f"status={report['status']}")
    workflow_status = report.get("workflow_status", report.get("workflows", {}))
    for name, status in sorted(workflow_status.items()):
        print(f"workflow_{name}={status}")
    if report["status"] == "PASS":
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
