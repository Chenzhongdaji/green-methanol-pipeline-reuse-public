#!/usr/bin/env python3
"""Run the public demand/supply preprocessing stage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from green_methanol_release.model.workflow import run_model_stage
from green_methanol_release.model.demand import DEMAND_INPUTS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if sorted(set(args.input)) != sorted(set(DEMAND_INPUTS.values())):
            raise ValueError("demand preprocessing inputs must match the public model registry")
        expected = ROOT / "data" / "processed" / "model_v01" / "demand_nodes.csv"
        if args.output.resolve() != expected.resolve():
            raise ValueError("demand preprocessing output must be the registered demand_nodes.csv")
        result = run_model_stage(ROOT, "demand_preprocessing", input_paths=args.input)
        print(json.dumps({"stage": "demand_preprocessing", "status": result.audit["status"]}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"error={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
