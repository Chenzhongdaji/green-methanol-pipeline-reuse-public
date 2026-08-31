"""Fail-closed contracts shared by public release workflows."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .safety import resolve_public_path

ALLOWED_WORKFLOW_STATUSES = {
    "reproduced",
    "aggregate-only",
    "hash-only",
    "not-run",
}


def safe_relative_path(value: str) -> PurePosixPath:
    """Return a repository-relative POSIX path or reject unsafe input."""

    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or ":" in value
        or "\\" in value
    ):
        raise ValueError(f"unsafe repository-relative path: {value}")
    return path


def validate_status(value: str) -> str:
    """Validate and return one of the closed workflow status values."""

    if value not in ALLOWED_WORKFLOW_STATUSES:
        raise ValueError(f"unsupported workflow status: {value}")
    return value


@dataclass(frozen=True)
class ReleaseRoot:
    """Resolve repository-relative paths without permitting root escape."""

    root: Path

    def resolve(self, value: str) -> Path:
        relative = safe_relative_path(value)
        return resolve_public_path(self.root, Path(*relative.parts))
