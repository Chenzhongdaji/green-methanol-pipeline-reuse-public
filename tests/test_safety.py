from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import green_methanol_release.audit as audit_module
from green_methanol_release.audit import audit_release
from green_methanol_release.safety import assert_public_path, audit_tracked_paths


@pytest.mark.parametrize(
    "path",
    [
        Path("data/管道数据/secret.csv"),
        Path("C:" + "\\" + "release" + "\\" + "管道数据" + "\\" + "secret.csv"),
        Path("data/one/管道数据/two/管道数据/file.csv"),
        Path("管道数据/file.csv"),
    ],
)
def test_assert_public_path_rejects_forbidden_component(path: Path):
    with pytest.raises(ValueError, match="管道数据"):
        assert_public_path(path)


@pytest.mark.parametrize(
    "path",
    [
        Path("data/管道数据_archive/file.csv"),
        Path("data/管道数据x/file.csv"),
        Path("data/前管道数据/file.csv"),
        Path("data/pipeline-data/file.csv"),
        Path("管道数据.csv"),
    ],
)
def test_assert_public_path_allows_near_matches(path: Path):
    assert_public_path(path)


def test_audit_tracked_paths_normalizes_separators_and_filters_exact_components():
    windows_separator = "\\"
    paths = [
        r"src\管道数据\secret.csv",
        "./data//管道数据/metadata.csv",
        "data/管道数据x/allowed.csv",
        "C:" + windows_separator + "release" + windows_separator + "管道数据" + windows_separator + "absolute.csv",
    ]

    assert audit_tracked_paths(paths) == [
        "C:" + "/" + "release" + "/" + "管道数据" + "/" + "absolute.csv",
        "data/管道数据/metadata.csv",
        "src/管道数据/secret.csv",
    ]


def test_audit_release_fails_when_index_contains_forbidden_component(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        audit_module,
        "_git_tracked_paths",
        lambda root: ["src/管道数据/secret.csv"],
    )
    monkeypatch.setattr(audit_module, "_validate_metadata", lambda root: [])
    monkeypatch.setattr(audit_module, "_scan_disclosures", lambda root, *args: {})
    monkeypatch.setattr(audit_module, "_check_licence_scope", lambda root: [])
    monkeypatch.setattr(
        audit_module,
        "run_reproduction",
        lambda root, mode, output: {"status": "PASS", "workflows": {}},
    )

    report = audit_release(Path.cwd(), require_manifest=False)

    assert report["status"] == "FAIL"
    assert report["tracked_forbidden_paths"] == ["src/管道数据/secret.csv"]
    assert any("tracked forbidden path" in error for error in report["errors"])


@pytest.mark.parametrize(
    "failure",
    [
        OSError("git is unavailable"),
        subprocess.CalledProcessError(1, ["git", "ls-files"]),
    ],
)
def test_audit_release_fails_closed_when_index_enumeration_fails(
    monkeypatch: pytest.MonkeyPatch, failure: BaseException
):
    def fail(*args: object, **kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(audit_module.subprocess, "run", fail)
    monkeypatch.setattr(audit_module, "_validate_metadata", lambda root: [])
    monkeypatch.setattr(audit_module, "_scan_disclosures", lambda root, *args: {})
    monkeypatch.setattr(audit_module, "_check_licence_scope", lambda root: [])
    monkeypatch.setattr(
        audit_module,
        "run_reproduction",
        lambda root, mode, output: {"status": "PASS", "workflows": {}},
    )

    report = audit_release(Path.cwd(), require_manifest=False)

    assert report["status"] == "FAIL"
    assert report["tracked_forbidden_paths"] == []
    assert any("tracked path audit failed" in error for error in report["errors"])


def test_payload_walk_is_globally_sorted(tmp_path: Path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    nested = tmp_path / "a"
    nested.mkdir()
    (nested / "nested.txt").write_text("nested", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")

    paths = [path.relative_to(tmp_path).as_posix() for path in audit_module._iter_payload_files(tmp_path)]

    assert paths == sorted(paths)
