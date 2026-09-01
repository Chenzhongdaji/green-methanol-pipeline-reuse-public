#!/usr/bin/env python3
"""Run public dynamic regional/logistics analysis."""

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
from green_methanol_release.model.analysis import ANALYSIS_INPUTS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if sorted(set(args.input)) != sorted(set(ANALYSIS_INPUTS.values())):
            raise ValueError("dynamic analysis inputs must match the public model registry")
        expected = ROOT / "data" / "processed" / "model_v01" / "analysis_summary.csv"
        if args.output.resolve() != expected.resolve():
            raise ValueError("analysis output must be the registered analysis_summary.csv")
        result = run_model_stage(ROOT, "dynamic_analysis", input_paths=args.input)
        print(json.dumps({"stage": "dynamic_analysis", "status": result.audit["status"]}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"error={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
