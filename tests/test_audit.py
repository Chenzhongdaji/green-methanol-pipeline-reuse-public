from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

import green_methanol_release.audit as audit_module
from green_methanol_release.audit import audit_release, verify_manifest_closure


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


@pytest.mark.parametrize("directory", ["build", "dist", "env", "qa/external"])
def test_common_payload_directories_are_not_silently_skipped(tmp_path: Path, directory: str):
    root = _copy_release(tmp_path, directory.replace("/", "_"))
    path = root / Path(*directory.split("/")) / "leak.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("token=gh" + "p_" + "A" * 36 + "\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert report["pre_manifest"] == "FAIL"
    assert path.relative_to(root).as_posix() in report["credential_hits"]


def test_scan_exclusions_are_explicit_and_limited_to_non_payload_caches():
    report = audit_release(ROOT, require_manifest=False)
    exclusions = set(report["scan_exclusions"])
    assert {".git", ".venv", "__pycache__", ".pytest_cache"} <= exclusions
    assert not exclusions.intersection({"env", "build", "dist", "qa/external", "qa/reports", "external_qa"})


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
    "payload",
    [
        "xox" + "b-" + "A" * 24,
        "gl" + "pat-" + "A" * 24,
        "npm" + "_" + "A" * 24,
        "Bearer " + "A" * 24,
        "password=" + "A" * 12,
    ],
)
def test_common_credential_variants_fail_closed(tmp_path: Path, payload: str):
    root = _copy_release(tmp_path, "credential_variant")
    path = root / "README.md"
    path.write_text(path.read_text(encoding="utf-8") + "\n" + payload + "\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert "README.md" in report["credential_hits"]


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


@pytest.mark.parametrize(
    "filename",
    [
        "candidate_links_v01.dbf",
        "candidate_links_v01.shx",
        "candidate_links_v01.prj",
        "refinery_to_pipeline_node_assignments_v01.csv",
        "airport_to_refinery_assignments.csv",
        "airport_to_refinery_assignment_v01.json",
    ],
)
def test_restricted_filename_singular_plural_and_gis_sidecars_fail_closed(tmp_path: Path, filename: str):
    root = _copy_release(tmp_path, filename.replace(".", "_"))
    path = root / "data" / filename
    path.write_text("placeholder\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert report["restricted_payload_hits"]


@pytest.mark.parametrize(
    "filename",
    [
        "pipeline_network_segment_v01.csv",
        "edge_flow_v01.csv",
        "physical_edge_v01.graphml",
        "physical_node_v01.csv",
        "candidate_links_v01.cpg",
        "candidate_links_v01.qpj",
        "candidate_links_v01.sbn",
        "candidate_links_v01.sbx",
        "candidate_links_v01.shp.xml",
        "standard_map_gs2023_2767_v01.pgw",
        "candidate_links_v01.gml",
        "candidate_links_v01.parquet",
    ],
)
def test_restricted_filename_singular_stems_fail_closed(tmp_path: Path, filename: str):
    root = _copy_release(tmp_path, filename.replace(".", "_"))
    path = root / "data" / filename
    path.write_text("placeholder\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert report["pre_manifest"] == "FAIL"
    assert any(filename in hit for hit in report["restricted_payload_hits"])


@pytest.mark.parametrize("suffix", ["tsv", "json"])
def test_restricted_schema_fields_are_parsed_in_tsv_and_json(tmp_path: Path, suffix: str):
    root = _copy_release(tmp_path, suffix)
    path = root / "data" / f"leak.{suffix}"
    if suffix == "tsv":
        payload = "node_id\tvalue\nnode-1\t1\n"
    else:
        payload = '[{"node_id": "node-1", "value": 1}]\n'
    path.write_text(payload, encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert any("node_id" in hit for hit in report["restricted_payload_hits"])


def test_restricted_schema_header_whitespace_is_normalized(tmp_path: Path):
    root = _copy_release(tmp_path)
    path = root / "data" / "spaced.tsv"
    path.write_text(" node_id \tvalue\nnode-1\t1\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert any("node_id" in hit for hit in report["restricted_payload_hits"])


def test_malformed_json_is_fail_closed(tmp_path: Path):
    root = _copy_release(tmp_path)
    path = root / "data" / "malformed.json"
    path.write_text("{not-json\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert "data/malformed.json" in report["format_hits"]


def test_doi_url_is_not_accepted_as_a_release_identifier(tmp_path: Path):
    root = _copy_release(tmp_path)
    path = root / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8") + "\nhttps://doi" + ".org/10." + "5281/example\n",
        encoding="utf-8",
        newline="\n",
    )
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert "README.md" in report["doi_hits"]


@pytest.mark.parametrize("relative", ["README.md", "DATA_AVAILABILITY.md", "CODE_AVAILABILITY.md"])
@pytest.mark.parametrize("payload", ["https://dx.doi" + ".org/10." + "1234/example", "10." + "1234/example"])
def test_release_metadata_rejects_doi_url_and_bare_doi_variants(
    tmp_path: Path, relative: str, payload: str
):
    root = _copy_release(tmp_path, relative.replace(".", "_") + payload[:4].replace("/", "_"))
    path = root / relative
    path.write_text(path.read_text(encoding="utf-8") + "\n" + payload + "\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert relative in report["doi_hits"]


def test_explicit_persistent_identifier_doi_is_rejected_but_public_source_doi_is_allowed(tmp_path: Path):
    root = _copy_release(tmp_path)
    source = root / "data" / "public_sources.csv"
    source_text = source.read_text(encoding="utf-8")
    source.write_text(
        source_text.replace(
            "external_sources.csv evidence_level=primary",
            "external_sources.csv evidence_level=primary; DOI 10." + "1234/literature",
            1,
        ),
        encoding="utf-8",
        newline="\n",
    )
    allowed = audit_release(root, require_manifest=False)
    assert allowed["status"] == "PASS"
    assert allowed["doi_hits"] == []

    persistent = root / "data" / "persistent_identifiers.csv"
    persistent.write_text(
        "persistent_identifier\n10." + "1234/release\n",
        encoding="utf-8",
        newline="\n",
    )
    rejected = audit_release(root, require_manifest=False)
    assert rejected["status"] == "FAIL"
    assert "data/persistent_identifiers.csv" in rejected["doi_hits"]


def test_cff_doi_field_is_not_accepted_as_a_release_identifier(tmp_path: Path):
    root = _copy_release(tmp_path)
    path = root / "CITATION.cff"
    path.write_text(
        path.read_text(encoding="utf-8") + "doi: 10." + "5281/example\n",
        encoding="utf-8",
        newline="\n",
    )
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert any("CITATION.cff" in error and "DOI" in error for error in report["errors"])


@pytest.mark.parametrize("relative", ["README.md", "DATA_AVAILABILITY.md", "CODE_AVAILABILITY.md"])
def test_public_release_metadata_requires_version(tmp_path: Path, relative: str):
    root = _copy_release(tmp_path, relative.replace(".", "_"))
    path = root / relative
    text = path.read_text(encoding="utf-8").replace("v1.0.0", "release-version")
    path.write_text(text, encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert any(relative in error and "version" in error for error in report["errors"])


@pytest.mark.parametrize("field", ["version", "date-released"])
def test_cff_requires_active_version_and_release_date_fields(tmp_path: Path, field: str):
    root = _copy_release(tmp_path, field.replace("-", "_"))
    path = root / "CITATION.cff"
    text = path.read_text(encoding="utf-8").replace(
        f"\n{field}: ", f"\n# {field}: ", 1
    )
    path.write_text(text, encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert any("CITATION.cff" in error and field in error for error in report["errors"])


@pytest.mark.parametrize("field", ["title", "repository-code"])
def test_cff_requires_active_title_and_repository_fields(tmp_path: Path, field: str):
    root = _copy_release(tmp_path, field.replace("-", "_"))
    path = root / "CITATION.cff"
    text = path.read_text(encoding="utf-8").replace(f"\n{field}:", f"\n# {field}:", 1)
    path.write_text(text, encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert any("CITATION.cff" in error and field in error for error in report["errors"])


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("title", "Wrong title"),
        ("type", "dataset"),
        ("license", "CC-BY-4.0"),
        ("repository-code", "https://example.invalid/release"),
    ],
)
def test_cff_active_target_fields_must_match(tmp_path: Path, field: str, replacement: str):
    root = _copy_release(tmp_path, field.replace("-", "_"))
    path = root / "CITATION.cff"
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(f"{field}:"):
            lines[index] = f'{field}: "{replacement}"' if field in {"title", "repository-code"} else f"{field}: {replacement}"
            break
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert any("CITATION.cff" in error and field in error for error in report["errors"])


@pytest.mark.parametrize("field", ["email", "affiliation", "orcid", "family-names", "given-names"])
def test_cff_rejects_personal_author_fields(tmp_path: Path, field: str):
    root = _copy_release(tmp_path, field.replace("-", "_"))
    path = root / "CITATION.cff"
    path.write_text(
        path.read_text(encoding="utf-8") + f"  {field}: not-permitted\n",
        encoding="utf-8",
        newline="\n",
    )
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert any("personal" in error.lower() for error in report["errors"])


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


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../outside.txt",
        "C:" + "/outside.txt",
        "/outside.txt",
        ".." + "\\outside.txt",
        "\\\\server\\share\\outside.txt",
    ],
)
def test_manifest_rejects_unsafe_path_before_external_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unsafe_path: str
):
    root = _copy_release(tmp_path)
    _write_manifest_fixture(root)
    outside = root.parent / "outside.txt"
    outside.write_text("outside sentinel\n", encoding="utf-8", newline="\n")
    manifest = root / "FILE_MANIFEST.csv"
    with manifest.open("a", encoding="utf-8", newline="") as handle:
        handle.write(f"{unsafe_path},17," + "a" * 64 + ",unsafe,MIT,text\n")

    resolved_reads: list[Path] = []
    original_sha256 = audit_module._sha256

    def guarded_sha256(path: Path) -> str:
        resolved_reads.append(path.resolve())
        assert root.resolve() in path.resolve().parents
        return original_sha256(path)

    monkeypatch.setattr(audit_module, "_sha256", guarded_sha256)
    report = verify_manifest_closure(root)
    assert report["status"] == "FAIL"
    assert any("unsafe manifest path" in error for error in report["errors"])
    assert outside.resolve() not in resolved_reads


def test_manifest_closure_includes_payload_like_directories(tmp_path: Path):
    root = _copy_release(tmp_path)
    _write_manifest_fixture(root)
    payload = root / "build" / "late_payload.txt"
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_text("late payload\n", encoding="utf-8", newline="\n")
    report = verify_manifest_closure(root)
    assert report["status"] == "FAIL"
    assert "build/late_payload.txt" in report["missing_files"]
