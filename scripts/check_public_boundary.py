#!/usr/bin/env python3
"""Reject exact private-directory components from the Git index."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

try:
    from green_methanol_release.safety import audit_tracked_paths
except ModuleNotFoundError:  # pragma: no cover - direct checkout execution
    _SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
    sys.path.insert(0, str(_SRC_ROOT))
    from green_methanol_release.safety import audit_tracked_paths


def _git_paths(root: Path) -> list[str]:
    """Read names from the index and non-ignored worktree without opening them."""

    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
        ],
        check=True,
        capture_output=True,
    )
    return [item.decode("utf-8", errors="surrogateescape") for item in result.stdout.split(b"\0") if item]


def forbidden_paths(paths: list[str]) -> list[str]:
    """Return exact-component violations without touching the filesystem."""

    return audit_tracked_paths(paths)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        paths = _git_paths(root)
        violations = forbidden_paths(paths)
    except (OSError, RuntimeError, subprocess.CalledProcessError, UnicodeError) as exc:
        print(f"public-boundary guard failed closed: {exc}", file=sys.stderr)
        return 2
    if violations:
        print("private directory path(s) are tracked or staged:", file=sys.stderr)
        for path in violations:
            print(path, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["forbidden_paths", "main"]
