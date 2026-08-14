from pathlib import Path

import pytest

from green_methanol_release.contracts import (
    ALLOWED_WORKFLOW_STATUSES,
    ReleaseRoot,
    safe_relative_path,
    validate_status,
)


def test_status_vocabulary_is_closed():
    assert ALLOWED_WORKFLOW_STATUSES == {
        "reproduced", "aggregate-only", "hash-only", "not-run"
    }
    with pytest.raises(ValueError, match="unsupported workflow status"):
        validate_status("PASS")


@pytest.mark.parametrize(
    "value",
    [
        "../secret.csv",
        "C:/Users/name/file.csv",
        "/home/name/file",
        r"folder\file.csv",
        r"\\server\share\file.csv",
    ],
)
def test_safe_relative_path_rejects_escape_and_absolute_paths(value):
    with pytest.raises(ValueError):
        safe_relative_path(value)


def test_release_root_refuses_writes_outside_root(tmp_path: Path):
    root = ReleaseRoot(tmp_path / "release")
    assert root.resolve("data/file.csv") == (tmp_path / "release" / "data" / "file.csv").resolve()
    with pytest.raises(ValueError):
        root.resolve("../outside.txt")
