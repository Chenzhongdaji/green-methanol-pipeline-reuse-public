#!/usr/bin/env python3
"""Build deterministic public Figure 2 panel carriers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from green_methanol_release.figures import build_figure_02


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--panel", choices=("e",))
    mode.add_argument("--panels", choices=("a-d,f-h",))
    args = parser.parse_args(argv)
    try:
        metadata = build_figure_02(
            args.input,
            args.output,
            panel=args.panel,
            panels=args.panels,
        )
    except (OSError, ValueError) as exc:
        print(f"error={exc}", file=sys.stderr)
        return 1
    print(json.dumps(metadata, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
