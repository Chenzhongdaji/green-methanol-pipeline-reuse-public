"""Path-safety guards for the public release boundary."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable


_FORBIDDEN_COMPONENT = "管道数据"
_SEPARATOR_RE = re.compile(r"/+")


def _as_text(path: Path | str) -> str:
    value = os.fspath(path)
    return os.fsdecode(value) if isinstance(value, bytes) else value


def _normalize_path(value: str) -> str:
    """Return a stable separator-normalized path without touching the filesystem."""

    normalized = _SEPARATOR_RE.sub("/", value.replace("\\", "/"))
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized == ".":
        return ""
    prefix = "/" if normalized.startswith("/") else ""
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    return prefix + "/".join(parts)


def _components(path: Path | str) -> tuple[str, ...]:
    normalized = _normalize_path(_as_text(path))
    return tuple(part for part in normalized.split("/") if part)


def assert_public_path(path: Path) -> None:
    """Reject paths that contain the exact excluded-directory component."""

    normalized = _normalize_path(_as_text(path))
    if _FORBIDDEN_COMPONENT in _components(normalized):
        raise ValueError(
            f"path enters excluded directory {_FORBIDDEN_COMPONENT!r}: {normalized}"
        )


def audit_tracked_paths(paths: Iterable[str]) -> list[str]:
    """Return sorted, normalized tracked paths entering the excluded directory.

    The check is deliberately string-only: callers may pass paths obtained from
    a Git index, and this function never checks existence or opens a path.
    """

    forbidden = {
        normalized
        for path in paths
        if _FORBIDDEN_COMPONENT in _components(path)
        for normalized in (_normalize_path(_as_text(path)),)
    }
    return sorted(forbidden)


__all__ = ["assert_public_path", "audit_tracked_paths"]
