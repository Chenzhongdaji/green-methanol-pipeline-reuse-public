from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from green_methanol_release.audit import audit_release


ROOT = Path(__file__).resolve().parents[1]


def _copy_release(tmp_path: Path, name: str = "release") -> Path:
    root = tmp_path / name
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache"))
    return root


def _write_manifest_fixture(root: Path) -> None:
    manifest = root / "FILE_MANIFEST.csv"
    excluded = {"FILE_MANIFEST.csv", "CHECKSUMS.sha256"}
    paths = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and not (set(path.relative_to(root).parts) & {".git", ".venv", "__pycache__", ".pytest_cache"})
        and path.name not in excluded
    )
    rows = ["path,bytes,sha256,purpose,licence_scope,data_class"]
    for relative in paths:
        payload = root / Path(*relative.split("/"))
        digest = hashlib.sha256(payload.read_bytes()).hexdigest()
        rows.append(f"{relative},{payload.stat().st_size},{digest},fixture,MIT,text")
    manifest.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    manifest_digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    checksum = root / "CHECKSUMS.sha256"
    checksum_rows = [
        f"{hashlib.sha256((root / Path(*relative.split('/'))).read_bytes()).hexdigest()}  {relative}"
        for relative in paths
    ]
    checksum_rows.append(f"{manifest_digest}  FILE_MANIFEST.csv")
    checksum.write_text("\n".join(checksum_rows) + "\n", encoding="utf-8", newline="\n")


def test_repository_passes_public_release_gates():
    report = audit_release(ROOT, require_manifest=False)
    assert report["status"] == "PASS"
    assert report["public_release"] == "BLOCKED_MANIFEST"
    assert report["pre_manifest"] == "PASS"
    assert report["level_2"] == "NOT_REPRODUCED"
    assert report["absolute_path_hits"] == []
    assert report["restricted_payload_hits"] == []


def test_release_has_separate_data_and_code_statements():
    assert (ROOT / "DATA_AVAILABILITY.md").is_file()
    assert (ROOT / "CODE_AVAILABILITY.md").is_file()


@pytest.mark.parametrize(
    ("relative", "payload"),
    [
        ("README.md", "fixture=C:" + "/" + "Users/author/private.txt"),
        ("README.md", "token=ghp_" + "A" * 36),
        ("data/controlled_inputs_metadata.csv", "candidate-link-geometry-v01.csv"),
    ],
)
def test_disclosure_mutations_fail_closed(tmp_path: Path, relative: str, payload: str):
    root = _copy_release(tmp_path)
    if relative == "data/controlled_inputs_metadata.csv":
        path = root / "data" / "candidate-link-geometry-v01.csv"
        path.write_text(payload + "\n", encoding="utf-8", newline="\n")
    else:
        path = root / relative
        path.write_text(path.read_text(encoding="utf-8") + "\n" + payload + "\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert report["pre_manifest"] == "FAIL"
    if relative == "README.md" and payload.startswith("fixture"):
        assert report["absolute_path_hits"]
    elif relative == "README.md":
        assert report["credential_hits"]
    elif relative == "data/controlled_inputs_metadata.csv":
        assert report["restricted_payload_hits"]


def test_all_zero_hash_mutation_fails_closed(tmp_path: Path):
    root = _copy_release(tmp_path)
    path = root / "data" / "controlled_inputs_metadata.csv"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace(",,hash_unavailable:", "," + "0" * 64 + ","), encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"


def test_dotfile_disclosure_is_scanned(tmp_path: Path):
    root = _copy_release(tmp_path)
    path = root / ".gitattributes"
    path.write_text(path.read_text(encoding="utf-8") + "\ntoken=gh" + "p_" + "A" * 36 + "\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert ".gitattributes" in report["credential_hits"]


@pytest.mark.parametrize(
    "filename",
    [
        "candidate_links.csv",
        "pipeline_network_segments_v01.csv",
        "standard_map_gs2023_2767.json",
        "physical_edges.graphml",
        "refinery_to_pipeline_node_assignment.csv",
    ],
)
def test_restricted_payload_filename_variants_fail_closed(tmp_path: Path, filename: str):
    root = _copy_release(tmp_path, filename.replace(".", "_"))
    path = root / "data" / filename
    path.write_text("placeholder\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert report["restricted_payload_hits"]


def test_orphan_manifest_row_fails_closed(tmp_path: Path):
    root = _copy_release(tmp_path)
    _write_manifest_fixture(root)
    manifest = root / "FILE_MANIFEST.csv"
    with manifest.open("a", encoding="utf-8", newline="") as handle:
        handle.write("missing.txt,1," + "a" * 64 + ",orphan,MIT,text\n")
    report = audit_release(root, require_manifest=True)
    assert report["status"] == "FAIL"
    assert "missing.txt" in report["manifest"]["orphan_files"]


def test_checksum_mismatch_fails_closed(tmp_path: Path):
    root = _copy_release(tmp_path)
    _write_manifest_fixture(root)
    checksums = root / "CHECKSUMS.sha256"
    checksums.write_text("0" * 64 + "  README.md\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=True)
    assert report["status"] == "FAIL"
    assert "README.md" in report["manifest"]["checksum_hash_mismatches"]


def test_manifest_rejects_negative_bytes_and_blank_scope(tmp_path: Path):
    root = _copy_release(tmp_path)
    _write_manifest_fixture(root)
    path = root / "FILE_MANIFEST.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    fields = lines[1].split(",")
    fields[1] = "-1"
    fields[3] = ""
    lines[1] = ",".join(fields)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=True)
    assert report["status"] == "FAIL"
    assert report["manifest"]["errors"]
