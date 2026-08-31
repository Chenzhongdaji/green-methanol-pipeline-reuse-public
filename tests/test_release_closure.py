from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from green_methanol_release.audit import audit_release, verify_manifest_closure
from green_methanol_release.inventory import (
    CHECKSUMS_FILENAME,
    MANIFEST_FILENAME,
    write_release_inventories,
)
from green_methanol_release.reproduce import run_reproduction


ROOT = Path(__file__).resolve().parents[1]


def _tracked_payload_paths(root: Path) -> set[str]:
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--"],
        check=True,
        capture_output=True,
    )
    return {
        item.decode("utf-8")
        for item in completed.stdout.split(b"\0")
        if item and item.decode("utf-8") not in {MANIFEST_FILENAME, CHECKSUMS_FILENAME}
    }


def _manifest_rows(root: Path) -> dict[str, dict[str, str]]:
    with (root / MANIFEST_FILENAME).open(encoding="utf-8", newline="") as handle:
        return {row["path"]: row for row in csv.DictReader(handle)}


def _checksum_rows(root: Path) -> dict[str, str]:
    return {
        path: digest
        for digest, _, path in (
            line.partition("  ")
            for line in (root / CHECKSUMS_FILENAME).read_text(encoding="utf-8").splitlines()
        )
        if path
    }


def test_manifest_and_checksum_cover_every_tracked_public_payload_once():
    manifest = _manifest_rows(ROOT)
    checksums = _checksum_rows(ROOT)
    tracked = _tracked_payload_paths(ROOT)

    assert set(manifest) == tracked
    assert set(checksums) == tracked | {MANIFEST_FILENAME}
    assert len(manifest) == len(tracked)
    assert len(checksums) == len(tracked) + 1


def test_manifest_attributes_are_bound_to_dataset_registry():
    manifest = _manifest_rows(ROOT)
    with (ROOT / "data" / "dataset_registry.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        datasets = list(csv.DictReader(handle))

    for row in datasets:
        entry = manifest[row["public_path"]]
        assert entry["purpose"] == row["role"]
        assert entry["licence_scope"] == row["license"]
        assert entry["data_class"] == row["origin"]


def test_manifest_regeneration_is_byte_deterministic(tmp_path: Path):
    release = tmp_path / "release"
    shutil.copytree(
        ROOT,
        release,
        ignore=shutil.ignore_patterns(
            ".git", ".venv", "__pycache__", ".pytest_cache", ".superpowers"
        ),
    )
    first_counts = write_release_inventories(release)
    first_manifest = (release / MANIFEST_FILENAME).read_bytes()
    first_checksums = (release / CHECKSUMS_FILENAME).read_bytes()
    second_counts = write_release_inventories(release)

    assert first_counts == second_counts
    assert first_manifest == (release / MANIFEST_FILENAME).read_bytes()
    assert first_checksums == (release / CHECKSUMS_FILENAME).read_bytes()


def test_audit_rejects_undeclared_payload_even_when_manifest_is_present(tmp_path: Path):
    release = tmp_path / "release"
    shutil.copytree(
        ROOT,
        release,
        ignore=shutil.ignore_patterns(
            ".git", ".venv", "__pycache__", ".pytest_cache", ".superpowers"
        ),
    )
    (release / "qa" / "undeclared_payload.txt").write_text(
        "new payload\n", encoding="utf-8", newline="\n"
    )

    report = verify_manifest_closure(release)

    assert report["status"] == "FAIL"
    assert "qa/undeclared_payload.txt" in report["missing_files"]


def test_audit_rejects_manifest_registry_attribute_drift(tmp_path: Path):
    release = tmp_path / "release"
    shutil.copytree(ROOT, release, ignore=shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", ".superpowers"))
    write_release_inventories(release)
    manifest = release / "FILE_MANIFEST.csv"
    text = manifest.read_text(encoding="utf-8")
    text = text.replace(
        "terminal figure-source carrier,CC BY 4.0,author-generated aggregate",
        "changed figure-source carrier,CC BY 4.0,author-generated aggregate",
        1,
    )
    manifest.write_text(text, encoding="utf-8", newline="\n")
    checksums = release / "CHECKSUMS.sha256"
    rows = []
    for line in checksums.read_text(encoding="utf-8").splitlines():
        if line.endswith("  FILE_MANIFEST.csv"):
            line = f"{hashlib.sha256(manifest.read_bytes()).hexdigest()}  FILE_MANIFEST.csv"
        rows.append(line)
    checksums.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")

    report = audit_release(release, require_manifest=True)

    assert report["status"] == "FAIL"
    assert any("manifest registry" in error for error in report["errors"])


def test_full_report_has_public_workflow_keys_and_figure2e_outputs(tmp_path: Path):
    report = run_reproduction(ROOT, "full", tmp_path / "full.json")

    assert report["status"] == "PASS"
    assert "level_1_status" not in report
    assert "level_2_status" not in report
    assert set(report["executed_output_ids"]) == {
        "figure-01",
        "figure-02a-d-f-h",
        "figure-02e",
        "figure-03",
        "figure-04",
        "figure-05",
    }
    assert report["artifacts"]["figure-02e"]["path"] == "figures/figure-02e.png"
    assert (ROOT / "figures" / "figure-02e.png").is_file()
    assert (ROOT / "figures" / "figure-02e.pdf").is_file()
    assert "NOT_REPRODUCED" not in json.dumps(report, ensure_ascii=False)


def test_public_metadata_binds_registry_and_full_reproduction_contract():
    metadata = "\n".join(
        (ROOT / name).read_text(encoding="utf-8")
        for name in (
            "README.md",
            "DATA_AVAILABILITY.md",
            "CODE_AVAILABILITY.md",
            "RELEASE_STATUS.md",
        )
    )
    dataset_registry = (ROOT / "data" / "dataset_registry.csv").read_text(
        encoding="utf-8"
    )
    output_registry = (ROOT / "data" / "output_registry.csv").read_text(
        encoding="utf-8"
    )

    assert "data/dataset_registry.csv" in metadata
    assert "data/output_registry.csv" in metadata
    assert "figures/figure-02e.png" in metadata
    assert "figures/figure-02e.pdf" in metadata
    assert "full_reproduction.json" in metadata
    assert "figure-02e" in output_registry
    assert "data/figure_source/figure-02.csv" in output_registry
    assert "figure-02-source-real" in dataset_registry


def test_audit_passes_public_release_gates_without_absolute_paths_or_disabled_status():
    report = audit_release(ROOT, require_manifest=False)

    assert report["status"] == "PASS"
    assert report["pre_manifest"] == "PASS"
    assert report["absolute_path_hits"] == []
    assert report["restricted_payload_hits"] == []
    assert report["errors"] == []


def test_audit_rejects_obsolete_release_status_wording(tmp_path: Path):
    release = tmp_path / "release"
    shutil.copytree(
        ROOT,
        release,
        ignore=shutil.ignore_patterns(
            ".git", ".venv", "__pycache__", ".pytest_cache", ".superpowers"
        ),
    )
    readme = release / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + "\nThis is a provisional candidate with NOT_REPRODUCED outputs.\n",
        encoding="utf-8",
        newline="\n",
    )

    report = audit_release(release, require_manifest=False)

    assert report["status"] == "FAIL"
    assert any("obsolete disabled wording" in error for error in report["errors"])
