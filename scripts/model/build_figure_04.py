#!/usr/bin/env python3
"""Regenerate model-derived Figure 4 from public model inputs."""

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
            raise ValueError("Figure 4 model inputs must match the public model registry")
        result = run_model_stage(ROOT, "figure_04")
        expected = ROOT / "figures" / "model-figure-04.png"
        if args.output.resolve() != expected.resolve():
            raise ValueError("Figure 4 model output must be the registered model-figure-04.png")
        print(json.dumps({"stage": "figure_04", "status": result.audit["status"]}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"error={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
