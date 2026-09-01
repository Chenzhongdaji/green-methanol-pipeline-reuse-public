#!/usr/bin/env python3
"""Regenerate model-derived Figure 5 from public model inputs."""

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
from green_methanol_release.model.analysis import ANALYSIS_FIGURE_SOURCES


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.input != [ANALYSIS_FIGURE_SOURCES["figure_05"]]:
            raise ValueError("Figure 5 model input must be the registered analysis source")
        result = run_model_stage(ROOT, "figure_05")
        expected = ROOT / "figures" / "model-figure-05.png"
        if args.output.resolve() != expected.resolve():
            raise ValueError("Figure 5 model output must be the registered model-figure-05.png")
        print(json.dumps({"stage": "figure_05", "status": result.audit["status"]}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"error={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
