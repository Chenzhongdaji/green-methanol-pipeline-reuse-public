#!/usr/bin/env python3
"""Run the public-release audit and write its report outside the repository."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from green_methanol_release.audit import audit_release


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--pre-manifest",
        action="store_true",
        help="run every gate except manifest/checksum closure",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output = args.output.resolve()
    if root == output or root in output.parents:
        print("error=the audit report must be outside the immutable repository", file=sys.stderr)
        return 1
    try:
        report = audit_release(root, require_manifest=not args.pre_manifest)
    except (OSError, ValueError) as exc:
        print(f"error={exc}", file=sys.stderr)
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"status={report['status']}")
    print(f"public_release={report['public_release']}")
    print(f"pre_manifest={report['pre_manifest']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
