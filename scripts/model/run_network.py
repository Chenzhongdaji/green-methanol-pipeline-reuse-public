#!/usr/bin/env python3
"""Run the public directed NetworkX flow stage."""

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
from green_methanol_release.model.network import NETWORK_STAGE_INPUTS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        expected_inputs = set(NETWORK_STAGE_INPUTS.values())
        if sorted(set(args.input)) != sorted(expected_inputs):
            raise ValueError("directed network inputs must match the public model registry")
        result = run_model_stage(ROOT, "directed_network_flow", input_paths=args.input)
        expected = ROOT / "data" / "processed" / "model_v01" / "network_summary.csv"
        if args.output.resolve() != expected.resolve():
            raise ValueError("network flow output must be the registered network_summary.csv")
        print(json.dumps({"stage": "directed_network_flow", "status": result.audit["status"]}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"error={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
