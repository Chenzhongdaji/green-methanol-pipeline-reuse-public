from __future__ import annotations

import csv
import hashlib
import json
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


def _update_map_registry(root: Path, **updates: str) -> None:
    registry = root / "data" / "dataset_registry.csv"
    with registry.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    assert fieldnames is not None
    row = next(item for item in rows if item["dataset_id"] == "standard-map-gs2023-2767")
    row.update(updates)
    with registry.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _rewrite_map_metadata(root: Path, metadata: object) -> None:
    path = root / "data" / "external" / "maps" / "standard_map_gs2023_2767.json"
    path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _update_map_registry(root, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def test_repository_passes_public_release_gates():
    report = audit_release(ROOT, require_manifest=False)
    assert report["status"] == "PASS"
    assert report["public_release"] == "BLOCKED_MANIFEST"
    assert report["pre_manifest"] == "PASS"
    assert report["offline_smoke"] == "PASS"
    assert "level_2" not in report
    assert report["absolute_path_hits"] == []
    assert report["restricted_payload_hits"] == []


def test_registered_copy_carrier_allows_byte_exact_lf_and_restricted_schema(tmp_path: Path):
    root = _copy_release(tmp_path, "registered_carrier")
    relative = "data/raw/pipeline/pipeline_network_segments_v01.csv"

    report = audit_release(root, require_manifest=False)

    assert report["status"] == "PASS"
    assert relative not in report["lf_hits"]
    assert not any(relative in hit for hit in report["restricted_payload_hits"])


def test_registered_restricted_carrier_requires_author_derived_public_provenance(
    tmp_path: Path,
):
    root = _copy_release(tmp_path, "unlicensed_registered_carrier")
    relative = "data/raw/pipeline/pipeline_network_segments_v01.csv"
    registry = root / "data" / "dataset_registry.csv"
    with registry.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    assert fieldnames is not None
    row = next(item for item in rows if item["public_path"] == relative)
    row["origin"] = "author-generated"
    row["access_route"] = "official catalogue"
    row["license"] = "third-party/not-relicensed"
    row["acquisition_command"] = "catalogue provenance"
    with registry.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    report = audit_release(root, require_manifest=False)

    assert report["status"] == "FAIL"
    assert any(relative in hit for hit in report["restricted_payload_hits"])
    assert "dataset registry carrier provenance is not author-derived" in report["errors"]


def test_final_audit_runs_full_workflow_and_requires_all_fixed_outputs(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[str] = []

    def fake_reproduction(root: Path, mode: str, output: Path) -> dict[str, object]:
        calls.append(mode)
        if mode == "smoke":
            return {"status": "PASS", "workflows": {}}
        return {
            "status": "PASS",
            "workflow_status": {"manuscript_outputs": "reproduced"},
            "executed_output_ids": ["figure-01"],
            "artifacts": {"figure-01": {"path": "figures/figure-01.png"}},
        }

    monkeypatch.setattr(audit_module, "run_reproduction", fake_reproduction)
    monkeypatch.setattr(audit_module, "_check_manifest_registry_alignment", lambda root: [])
    monkeypatch.setattr(
        audit_module,
        "verify_manifest_closure",
        lambda root: {"status": "PASS"},
    )

    report = audit_release(ROOT, require_manifest=True)

    assert calls == ["smoke", "full"]
    assert report["status"] == "FAIL"
    assert report["offline_full"] == "PASS"
    assert report["full_reproduction"]["executed_output_ids"] == ["figure-01"]
    assert any("all registered output IDs" in error for error in report["errors"])


def test_unregistered_restricted_name_and_schema_still_fail(tmp_path: Path):
    root = _copy_release(tmp_path, "unregistered_carrier")
    relative = "data/unregistered/pipeline_network_segments_v01.csv"
    path = root / Path(*relative.split("/"))
    path.parent.mkdir(parents=True)
    path.write_bytes(b"from_lon,from_lat,to_lon,to_lat\r\n0,0,1,1\r\n")

    report = audit_release(root, require_manifest=False)

    assert report["status"] == "FAIL"
    assert any(relative in hit for hit in report["restricted_payload_hits"])


def test_registered_carrier_hash_mismatch_is_not_exempt(tmp_path: Path):
    root = _copy_release(tmp_path, "mismatched_carrier")
    relative = "data/raw/pipeline/pipeline_network_segments_v01.csv"
    path = root / Path(*relative.split("/"))
    path.write_bytes(path.read_bytes() + b"\n")

    report = audit_release(root, require_manifest=False)

    assert report["status"] == "FAIL"
    assert any(relative in hit for hit in report["restricted_payload_hits"])
    assert "dataset registry carrier hash mismatch" in report["errors"]


def test_acquire_metadata_carrier_hash_mismatch_is_not_exempt(tmp_path: Path):
    root = _copy_release(tmp_path, "mismatched_acquire_metadata")
    relative = "data/external/maps/standard_map_gs2023_2767.json"
    path = root / Path(*relative.split("/"))
    path.write_bytes(path.read_bytes() + b" \r\n")

    report = audit_release(root, require_manifest=False)

    assert report["status"] == "FAIL"
    assert relative in report["lf_hits"]
    assert any(relative in hit for hit in report["restricted_payload_hits"])
    assert "dataset registry carrier hash mismatch" in report["errors"]


def test_acquire_metadata_non_json_path_is_not_exempt(tmp_path: Path):
    root = _copy_release(tmp_path, "non_json_acquire_metadata")
    relative = "data/external/maps/standard_map_gs2023_2767.json"
    _update_map_registry(
        root,
        public_path="data/external/maps/standard_map_gs2023_2767.shp",
    )

    report = audit_release(root, require_manifest=False)

    assert report["status"] == "FAIL"
    assert relative not in report["lf_hits"]
    assert any(relative in hit for hit in report["restricted_payload_hits"])
    assert "dataset registry acquire metadata carrier validation failed" in report["errors"]


def test_acquire_metadata_keyword_field_is_not_exempt(tmp_path: Path):
    root = _copy_release(tmp_path, "keyword_acquire_metadata")
    metadata = json.loads(
        (root / "data" / "external" / "maps" / "standard_map_gs2023_2767.json").read_text(
            encoding="utf-8"
        )
    )
    metadata["payload_blob_geometry"] = {"value": "not a boundary payload"}
    _rewrite_map_metadata(root, metadata)

    report = audit_release(root, require_manifest=False)

    assert report["status"] == "FAIL"
    assert "dataset registry acquire metadata carrier validation failed" in report["errors"]


def test_acquire_metadata_bad_json_is_not_exempt(tmp_path: Path):
    root = _copy_release(tmp_path, "bad_json_acquire_metadata")
    path = root / "data" / "external" / "maps" / "standard_map_gs2023_2767.json"
    path.write_text('{"review_number": "GS(2023)2767"\n', encoding="utf-8", newline="\n")
    _update_map_registry(root, sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    report = audit_release(root, require_manifest=False)

    assert report["status"] == "FAIL"
    assert "dataset registry acquire metadata carrier validation failed" in report["errors"]


def test_acquire_metadata_local_reference_is_not_exempt(tmp_path: Path):
    root = _copy_release(tmp_path, "local_reference_acquire_metadata")
    metadata = json.loads(
        (root / "data" / "external" / "maps" / "standard_map_gs2023_2767.json").read_text(
            encoding="utf-8"
        )
    )
    metadata["local_reference_files"] = ["official-map.shp"]
    _rewrite_map_metadata(root, metadata)

    report = audit_release(root, require_manifest=False)

    assert report["status"] == "FAIL"
    assert "dataset registry acquire metadata carrier validation failed" in report["errors"]


@pytest.mark.parametrize(
    ("payload", "report_key"),
    [
        ("token=gh" + "p_" + "A" * 36, "credential_hits"),
        ("path=C:" + "/" + "Users/author/private.txt", "absolute_path_hits"),
    ],
)
def test_registered_carrier_still_scans_sensitive_disclosures(
    tmp_path: Path, payload: str, report_key: str
):
    root = _copy_release(tmp_path, report_key)
    relative = "data/raw/pipeline/pipeline_network_segments_v01.csv"
    path = root / Path(*relative.split("/"))
    path.write_text(
        path.read_text(encoding="utf-8") + "\n" + payload + "\n",
        encoding="utf-8",
        newline="\n",
    )

    report = audit_release(root, require_manifest=False)

    assert report["status"] == "FAIL"
    assert relative in report[report_key]


def test_release_has_separate_data_and_code_statements():
    assert (ROOT / "DATA_AVAILABILITY.md").is_file()
    assert (ROOT / "CODE_AVAILABILITY.md").is_file()


def test_current_candidate_has_no_old_repository_or_manuscript_binding():
    texts = "\n".join(
        (ROOT / name).read_text(encoding="utf-8")
        for name in (
            "README.md",
            "DATA_AVAILABILITY.md",
            "CODE_AVAILABILITY.md",
            "MANUSCRIPT_SCOPE.md",
            "CITATION.cff",
            "NOTICE.md",
            "RELEASE_STATUS.md",
        )
    )
    assert "7_27" + ".git" not in texts
    assert "green_methanol_pipeline_reuse_" + "v1.21_en.docx" not in texts
    assert "d6c9cec04888efdcd125ef946edad139990e81fb630afc11c7fe94bb2cca" + "4f6a" not in texts
    assert "green_methanol_manuscript_references_v02_2026-08-14_rev04_public_data_code_2026-08-22.docx" in texts
    assert "green_methanol_supplementary_information_rev04_public_data_code_2026-08-22.docx" in texts


def test_current_release_binds_figure2e_to_public_registry_and_outputs():
    registry = (ROOT / "data" / "output_registry.csv").read_text(encoding="utf-8")
    metadata = "\n".join(
        (ROOT / name).read_text(encoding="utf-8")
        for name in ("README.md", "DATA_AVAILABILITY.md", "CODE_AVAILABILITY.md", "RELEASE_STATUS.md")
    )
    assert "figure-02e" in registry
    assert "data/figure_source/figure-02.csv" in registry
    assert "figures/figure-02e.png" in registry
    assert "figures/figure-02e.pdf" in metadata
    assert "full_reproduction.json" in metadata


def test_public_registry_has_provenance_and_rights_contract():
    registry = (ROOT / "data" / "dataset_registry.csv").read_text(encoding="utf-8")
    assert "dataset_id,public_path,role,origin,access_route,license" in registry
    assert "repository carrier" in registry
    assert "third-party/not-relicensed" in registry


def test_license_data_rejects_controlled_metadata_grant(tmp_path: Path):
    root = _copy_release(tmp_path)
    path = root / "LICENSE-DATA"
    text = path.read_text(encoding="utf-8")
    text += "\n- `data/dataset_registry.csv` (CC BY 4.0)\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert any("LICENSE-DATA" in error for error in report["errors"])


def test_license_data_rejects_plaintext_public_source_metadata_grant(tmp_path: Path):
    root = _copy_release(tmp_path, "license_plaintext_boundary")
    path = root / "LICENSE-DATA"
    text = path.read_text(encoding="utf-8")
    text += "\nCC BY 4.0 covers data/public_sources.csv.\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert any("LICENSE-DATA" in error for error in report["errors"])


def test_license_data_rejects_plaintext_third_party_path(tmp_path: Path):
    root = _copy_release(tmp_path, "license_plaintext_third_party")
    path = root / "LICENSE-DATA"
    text = path.read_text(encoding="utf-8")
    text += "\nCC BY 4.0 covers external/third_party_payload.csv.\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert any("LICENSE-DATA" in error for error in report["errors"])


@pytest.mark.parametrize(
    "payload",
    [
        "CC BY covers data\\public_sources.csv.",
        "CC BY covers .\\data\\public_sources.csv.",
        "CC BY covers data//public_sources.csv.",
        "CC BY covers external\\third_party_payload.csv.",
        "CC BY covers .\\external//third_party_payload.csv.",
        "CC BY covers ../data/public_sources.csv.",
        "CC BY covers /data/public_sources.csv.",
        "CC BY covers C:\\data\\public_sources.csv.",
        "CC BY covers \\\\server\\share\\data\\public_sources.csv.",
        "CC BY covers C:\\data\\author_derived\\terminal_gap_aggregate.csv.",
        "CC BY covers data/author_derived/terminal_gap_aggregate.csv?foo.",
        "CC BY covers data/author_derived/terminal_gap_aggregate.csv#foo.",
        "CC BY covers data/author_derived/terminal_gap_aggregate.csv:foo.",
        "CC BY covers data/author_derived/terminal_gap_aggregate.csv extra.",
    ],
)
def test_license_data_normalizes_and_rejects_unauthorized_paths(tmp_path: Path, payload: str):
    root = _copy_release(tmp_path, "license_path_normalization")
    path = root / "LICENSE-DATA"
    path.write_text(path.read_text(encoding="utf-8") + "\n" + payload + "\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert any("LICENSE-DATA" in error for error in report["errors"])


@pytest.mark.parametrize(
    "payload",
    [
        "Controlled/restricted data included under CC BY 4.0.",
        "The controlled metadata is covered by CC BY 4.0.",
        "CC BY covers external/third_party_payload.csv.",
        "Third_party data is included under CC BY 4.0.",
    ],
)
def test_notice_rejects_controlled_or_restricted_inclusion(tmp_path: Path, payload: str):
    root = _copy_release(tmp_path, "notice_boundary")
    path = root / "NOTICE.md"
    path.write_text(path.read_text(encoding="utf-8") + "\n" + payload + "\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert any("NOTICE.md" in error and "exclude" in error.lower() for error in report["errors"])


@pytest.mark.parametrize(
    "relative",
    [
        "data/public_sources.csv",
        "data/dictionaries/output_registry.md",
        "external/third_party_payload.csv",
    ],
)
def test_license_data_allowlist_rejects_public_or_controlled_metadata_paths(tmp_path: Path, relative: str):
    root = _copy_release(tmp_path, relative.replace("/", "_"))
    path = root / "LICENSE-DATA"
    text = path.read_text(encoding="utf-8") + f"\n- `{relative}`\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert any("LICENSE-DATA" in error and "allowlist" in error for error in report["errors"])


def test_code_license_must_remain_mit_boundary(tmp_path: Path):
    root = _copy_release(tmp_path)
    path = root / "LICENSE"
    path.write_text(path.read_text(encoding="utf-8") + "\nCC BY 4.0 applies to all code.\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert any("LICENSE" in error and "MIT" in error for error in report["errors"])


def test_pyproject_requires_release_version(tmp_path: Path):
    root = _copy_release(tmp_path)
    path = root / "pyproject.toml"
    text = path.read_text(encoding="utf-8").replace('version = "1.0.0"', 'version = "0.9.0"', 1)
    path.write_text(text, encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert any("pyproject.toml" in error and "version" in error.lower() for error in report["errors"])


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
        ("data/unregistered/candidate-link-geometry-v01.csv", "candidate-link-geometry-v01.csv"),
    ],
)
def test_disclosure_mutations_fail_closed(tmp_path: Path, relative: str, payload: str):
    root = _copy_release(tmp_path)
    if relative.startswith("data/unregistered/"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("from_lon,from_lat,to_lon,to_lat\n0,0,1,1\n" + payload + "\n", encoding="utf-8", newline="\n")
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
    elif relative.startswith("data/unregistered/"):
        assert report["restricted_payload_hits"]


def test_all_zero_hash_mutation_fails_closed(tmp_path: Path):
    root = _copy_release(tmp_path)
    _update_map_registry(root, sha256="0" * 64)
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert "dataset registry carrier hash mismatch" in report["errors"]


def test_dotfile_disclosure_is_scanned(tmp_path: Path):
    root = _copy_release(tmp_path)
    path = root / ".gitattributes"
    path.write_text(path.read_text(encoding="utf-8") + "\ntoken=gh" + "p_" + "A" * 36 + "\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert ".gitattributes" in report["credential_hits"]


@pytest.mark.parametrize(
    ("filename", "payload", "hit_key"),
    [
        (".env", "TOKEN=gh" + "p_" + "A" * 36, "credential_hits"),
        (".npmrc", "//registry.npmjs.org/:_authToken=gh" + "p_" + "A" * 36, "credential_hits"),
        (".pypirc", "password=" + "A" * 12, "credential_hits"),
        ("Dockerfile", "ENV SECRET=gh" + "p_" + "A" * 36, "credential_hits"),
        ("Makefile", "TOKEN=gh" + "p_" + "A" * 36, "credential_hits"),
        ("credentials", "path=C:" + "/" + "Users/author/private.txt", "absolute_path_hits"),
        ("config", "Bearer " + "A" * 24, "credential_hits"),
    ],
)
def test_known_extensionless_text_names_are_scanned(
    tmp_path: Path, filename: str, payload: str, hit_key: str
):
    root = _copy_release(tmp_path, filename.replace(".", "_"))
    path = root / filename
    # The release now legitimately contains a top-level ``config/`` directory.
    # Replace it in this isolated fixture so the extensionless-file scanner can
    # still exercise the exact historical filename ``config``.
    if path.is_dir():
        shutil.rmtree(path)
    path.write_text(payload + "\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert filename in report[hit_key]


def test_known_extensionless_text_restricted_token_is_scanned(tmp_path: Path):
    root = _copy_release(tmp_path, "extensionless_restricted")
    path = root / "config"
    if path.is_dir():
        shutil.rmtree(path)
    path.write_text("candidate_links_v01.csv\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert "config" in report["restricted_payload_hits"]


@pytest.mark.parametrize(
    "filename",
    [
        ".env.local",
        ".ENV",
        ".npmrc.local",
        ".pypirc.local",
        "dockerfile",
        "makefile",
        "Credentials",
        "config.local",
        ".gitconfig",
    ],
)
def test_dotfile_and_case_variants_are_sniffed(tmp_path: Path, filename: str):
    root = _copy_release(tmp_path, filename.replace(".", "_"))
    path = root / filename
    path.write_text("token=gh" + "p_" + "A" * 36 + "\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert filename in report["credential_hits"]


def test_unknown_small_utf8_file_is_sniffed(tmp_path: Path):
    root = _copy_release(tmp_path, "unknown_text")
    path = root / "mystery.payload"
    path.write_text("path=C:" + "/" + "Users/author/private.txt\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert "mystery.payload" in report["absolute_path_hits"]


def test_unknown_utf8_payload_over_four_megabytes_is_still_scanned(tmp_path: Path):
    root = _copy_release(tmp_path, "large_unknown_text")
    path = root / "large.payload"
    payload = "A" * (4 * 1024 * 1024 + 1) + "\ntoken=gh" + "p_" + "A" * 36 + "\n"
    path.write_text(payload, encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert "large.payload" in report["credential_hits"]


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
        "candidate_links_v01",
        "candidate_links",
        "pipeline_network_segment_v01",
        "candidate_links_v01.csv~",
        ".candidate_links_v01.csv",
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


@pytest.mark.parametrize("suffix", ["csv", "tsv"])
def test_restricted_schema_header_bom_is_normalized(tmp_path: Path, suffix: str):
    root = _copy_release(tmp_path, "bom_schema")
    delimiter = "," if suffix == "csv" else "\t"
    path = root / "data" / f"bom.{suffix}"
    path.write_text(f"\ufeffnode_id{delimiter}value\nnode-1{delimiter}1\n", encoding="utf-8", newline="\n")
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
    text = path.read_text(encoding="utf-8").replace("1.0.0", "release-version")
    path.write_text(text, encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert any(relative in error and "version" in error for error in report["errors"])


@pytest.mark.parametrize("field", ["version"])
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


@pytest.mark.parametrize("field", ["date-released", "url"])
def test_cff_rejects_public_release_locator_fields(tmp_path: Path, field: str):
    root = _copy_release(tmp_path, f"cff-{field.replace('-', '_')}")
    path = root / "CITATION.cff"
    value = "2026-08-22" if field == "date-released" else "https://example.invalid/not-assigned"
    path.write_text(path.read_text(encoding="utf-8") + f"{field}: {value}\n", encoding="utf-8", newline="\n")
    report = audit_release(root, require_manifest=False)
    assert report["status"] == "FAIL"
    assert any("CITATION.cff" in error and "archival release" in error for error in report["errors"])


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
