from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from green_methanol_release.audit import audit_release, verify_manifest_closure
from green_methanol_release.inventory import (
    CHECKSUMS_FILENAME,
    EXPECTED_OUTPUT_IDS,
    MANIFEST_FILENAME,
    write_release_inventories,
)
from green_methanol_release.reproduce import run_reproduction


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_BOUNDARY_FILES = (
    "MANUSCRIPT_SCOPE.md",
    "figures/panel_map.csv",
    "data/dictionaries/panel_map.md",
    "data/author_derived/figure2_aggregate_source.csv",
    "data/dictionaries/figure2_aggregate_source.md",
    "data/dictionaries/figure_02.md",
    "data/dataset_registry.csv",
    "data/output_registry.csv",
    "data/dictionaries/dataset_registry.md",
    "data/dictionaries/output_registry.md",
)
LEGACY_BOUNDARY_MARKERS = (
    "provisional candidate",
    "offline candidate",
    "restricted-map-not-released",
    "unavailable",
    "withheld",
    "interim",
)


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


def test_registry_carrier_hashes_match_a_clean_lf_checkout(tmp_path: Path):
    archive = tmp_path / "release.tar"
    clean = tmp_path / "clean-checkout"
    subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "archive",
            "--format=tar",
            f"--output={archive}",
            "HEAD",
        ],
        check=True,
    )
    clean.mkdir()
    with tarfile.open(archive) as package:
        package.extractall(clean, filter="data")

    with (ROOT / "data" / "dataset_registry.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if row["stage_action"] not in {"copy", "existing"}:
            continue
        relative = Path(*row["public_path"].split("/"))
        current = ROOT / relative
        archived = clean / relative
        assert current.is_file(), row["public_path"]
        assert archived.is_file(), row["public_path"]
        current_bytes = current.read_bytes()
        archived_bytes = archived.read_bytes()
        assert b"\r" not in current_bytes
        assert b"\r" not in archived_bytes
        assert current_bytes == archived_bytes
        assert hashlib.sha256(current_bytes).hexdigest() == row["sha256"]


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

    with (ROOT / "data" / "output_registry.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        outputs = list(csv.DictReader(handle))
    for row in outputs:
        artifacts = [row["expected_artifact"]]
        artifacts.extend(
            item for item in row["secondary_artifacts"].split(";") if item
        )
        for artifact in artifacts:
            entry = manifest[artifact]
            assert entry["purpose"] == f"manuscript output: {row['manuscript_location']}"
            assert entry["licence_scope"] == "generated artifact; see registered inputs"
            assert entry["data_class"] == "manuscript output"


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
    first_root = tmp_path / "independent-a"
    second_root = tmp_path / "independent-b"
    first_report_path = first_root / "full_reproduction.json"
    second_report_path = second_root / "full_reproduction.json"
    report = run_reproduction(ROOT, "full", first_report_path)
    second_report = run_reproduction(ROOT, "full", second_report_path)

    assert report["status"] == "PASS"
    assert second_report == report
    assert first_report_path.read_bytes() == second_report_path.read_bytes()
    assert report["artifacts"] == second_report["artifacts"]
    assert (first_root / "logs").is_dir()
    assert (second_root / "logs").is_dir()
    assert first_root != second_root
    assert "level_1_status" not in report
    assert "level_2_status" not in report
    assert set(report["executed_output_ids"]) == set(EXPECTED_OUTPUT_IDS)
    assert report["artifacts"]["figure-02e"]["path"] == "figures/figure-02e.png"
    assert report["artifacts"]["figure-02e"]["secondary_artifacts"][0]["path"] == (
        "figures/figure-02e.pdf"
    )
    assert len(report["artifacts"]["figure-02e"]["secondary_artifacts"][0]["sha256"]) == 64
    assert (ROOT / "figures" / "figure-02e.png").is_file()
    assert (ROOT / "figures" / "figure-02e.pdf").is_file()
    assert "NOT_REPRODUCED" not in json.dumps(report, ensure_ascii=False)


def test_fresh_figure2e_pdf_digest_matches_full_report(tmp_path: Path):
    report_path = tmp_path / "fresh-full" / "full_reproduction.json"
    report = run_reproduction(ROOT, "full", report_path)
    fresh_png = tmp_path / "fresh-figure-02e.png"
    subprocess.run(
        [
            sys.executable,
            "scripts/build_figure_02.py",
            "--panel",
            "e",
            "--input",
            "data/figure_source/figure-02.csv",
            "--output",
            str(fresh_png),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    fresh_pdf = fresh_png.with_suffix(".pdf")
    fresh_digest = hashlib.sha256(fresh_pdf.read_bytes()).hexdigest()
    report_digest = report["artifacts"]["figure-02e"]["secondary_artifacts"][0]["sha256"]
    assert report_digest == fresh_digest


def test_figure2_panel_map_binds_executable_registry_inputs():
    with (ROOT / "figures" / "panel_map.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        panel_rows = [row for row in csv.DictReader(handle) if row["figure"] == "Figure 2"]
    assert {row["panel"] for row in panel_rows} == {"a-d,f-h", "e"}
    assert all(
        row["source_data"] == "data/figure_source/figure-02.csv"
        and row["dictionary"] == "data/dictionaries/figure_02.md"
        for row in panel_rows
    )
    assert "aggregate-derived evidence is supplementary" in next(
        row["reason"] for row in panel_rows if row["panel"] == "a-d,f-h"
    )

    with (ROOT / "data" / "output_registry.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        outputs = {row["output_id"]: row for row in csv.DictReader(handle)}
    for output_id in ("figure-02a-d-f-h", "figure-02e"):
        output = outputs[output_id]
        assert output["input_dataset_ids"] == "figure-02-source-real"
        assert "--input data/figure_source/figure-02.csv" in output["generation_command"]

    panel_map_dictionary = (
        ROOT / "data" / "dictionaries" / "panel_map.md"
    ).read_text(encoding="utf-8")
    normalized_panel_map_dictionary = " ".join(panel_map_dictionary.split())
    assert "Figure 2 panels a-d and f-h use the direct executable carrier" in normalized_panel_map_dictionary
    assert "Figure 2e uses the same direct executable carrier" in normalized_panel_map_dictionary
    assert "`data/figure_source/figure-02.csv`" in normalized_panel_map_dictionary
    assert "`data/dictionaries/figure_02.md`" in normalized_panel_map_dictionary
    assert "`figure-02-source-real`" in normalized_panel_map_dictionary
    assert "supplementary derived evidence only" in normalized_panel_map_dictionary
    assert "not a direct builder input" in normalized_panel_map_dictionary



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


def test_public_boundary_files_use_the_current_figure2e_contract():
    text = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8")
        for relative in PUBLIC_BOUNDARY_FILES
    ).casefold()

    assert not any(marker in text for marker in LEGACY_BOUNDARY_MARKERS)
    panel_map = (ROOT / "figures" / "panel_map.csv").read_text(encoding="utf-8")
    assert "Figure 2,e,aggregate-only,data/figure_source/figure-02.csv" in panel_map
    assert "figure-02-source-real" in (
        ROOT / "data" / "dictionaries" / "figure2_aggregate_source.md"
    ).read_text(encoding="utf-8")
    assert "figures/figure-02e.pdf" in (
        ROOT / "data" / "dictionaries" / "output_registry.md"
    ).read_text(encoding="utf-8")


def test_audit_rejects_legacy_boundary_wording_in_each_public_contract_file(
    tmp_path: Path,
):
    for index, relative in enumerate(PUBLIC_BOUNDARY_FILES):
        release = tmp_path / f"release-{index}"
        shutil.copytree(
            ROOT,
            release,
            ignore=shutil.ignore_patterns(
                ".git", ".venv", "__pycache__", ".pytest_cache", ".superpowers"
            ),
        )
        path = release / Path(*relative.split("/"))
        path.write_text(
            path.read_text(encoding="utf-8") + "\ninterim unavailable wording\n",
            encoding="utf-8",
            newline="\n",
        )

        report = audit_release(release, require_manifest=False)

        assert report["status"] == "FAIL"
        assert any(relative in error and "legacy" in error for error in report["errors"])


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
