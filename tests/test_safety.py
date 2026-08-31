from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import green_methanol_release.audit as audit_module
import green_methanol_release.inventory as inventory_module
import green_methanol_release.reproduce as reproduce_module
import green_methanol_release.safety as safety_module
from green_methanol_release.audit import audit_release
from green_methanol_release.reproduce import run_reproduction
from green_methanol_release.safety import (
    assert_public_path,
    audit_tracked_paths,
    resolve_public_path,
)


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


def test_resolve_public_path_rejects_symlink_alias_to_excluded_component(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(safety_module, "_FORBIDDEN_COMPONENT", "blocked-component")
    blocked = tmp_path / "blocked-component"
    blocked.mkdir()
    (blocked / "secret.txt").write_text("secret", encoding="utf-8", newline="\n")
    alias = tmp_path / "public-alias"
    try:
        alias.symlink_to(blocked, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(ValueError, match="excluded directory"):
        resolve_public_path(tmp_path, alias / "secret.txt")


def test_inventory_loader_resolves_before_reading_symlink_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(safety_module, "_FORBIDDEN_COMPONENT", "blocked-component")
    blocked = tmp_path / "blocked-component"
    blocked.mkdir()
    source = blocked / "public_sources.csv"
    source.write_text("source_id\nsecret\n", encoding="utf-8", newline="\n")
    alias = tmp_path / "public_sources.csv"
    try:
        alias.symlink_to(source)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(ValueError, match="excluded directory"):
        inventory_module.load_public_sources(alias)


def test_full_report_rejects_symlink_alias_to_excluded_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(safety_module, "_FORBIDDEN_COMPONENT", "blocked-component")
    blocked = tmp_path / "blocked-component"
    blocked.mkdir()
    target = blocked / "report.json"
    alias = tmp_path / "report.json"
    try:
        alias.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    monkeypatch.setattr(
        reproduce_module,
        "run_full",
        lambda root, output_root: {"status": "PASS", "mode": "full"},
    )

    report = run_reproduction(tmp_path, "full", alias)

    assert report["status"] == "PASS"
    assert not target.exists()


def test_inventory_walker_fails_closed_on_walk_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def failing_walk(*args: object, **kwargs: object):
        assert "onerror" in kwargs
        callback = kwargs["onerror"]
        assert callable(callback)
        callback(OSError("permission denied"))
        return iter(())

    monkeypatch.setattr(inventory_module.os, "walk", failing_walk)

    with pytest.raises(ValueError, match="walk"):
        inventory_module._relative_payload_files(tmp_path)


def test_audit_walker_fails_closed_on_walk_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def failing_walk(*args: object, **kwargs: object):
        assert "onerror" in kwargs
        callback = kwargs["onerror"]
        assert callable(callback)
        callback(OSError("permission denied"))
        return iter(())

    monkeypatch.setattr(audit_module.os, "walk", failing_walk)

    with pytest.raises(RuntimeError, match="payload walk"):
        list(audit_module._iter_payload_files(tmp_path))
