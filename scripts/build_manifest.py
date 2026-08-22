#!/usr/bin/env python3
"""Regenerate the deterministic release manifest and checksum inventory."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from green_methanol_release.inventory import write_release_inventories


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    counts = write_release_inventories(args.root.resolve())
    print(f"manifest_rows={counts['manifest_rows']}")
    print(f"checksum_rows={counts['checksum_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
