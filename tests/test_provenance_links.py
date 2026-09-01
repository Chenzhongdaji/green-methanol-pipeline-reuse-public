from __future__ import annotations

import csv
import hashlib
from pathlib import Path
import shutil

import pytest

from green_methanol_release.audit import audit_release
from green_methanol_release.provenance import validate_repository_provenance


ROOT = Path(__file__).resolve().parents[1]


def test_public_provenance_links_resolve_or_are_explicit_historical_metadata():
    report = validate_repository_provenance(ROOT)

    assert report["status"] == "PASS"
    assert report["errors"] == []
    assert report["direct_public_carrier_count"] == 7
    assert report["historical_metadata_only_count"] == 7
    assert report["unresolved_direct_links"] == []
    assert report["hash_mismatches"] == []


def test_c3_rows_use_historical_metadata_when_legacy_flow_path_is_unavailable():
    path = ROOT / "data" / "processed" / "dynamic_analyses_v08" / "c3_unlocking_cost.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 27
    assert {row["flow_source"] for row in rows} == {
        "historical://data/derived/selected_plan_flow_recompute_v01.csv"
    }
    assert {row["flow_source_status"] for row in rows} == {"historical_metadata_only"}


def test_audit_exposes_public_provenance_gate():
    report = audit_release(ROOT, require_manifest=False)

    assert report["status"] == "PASS"
    assert report["provenance"]["status"] == "PASS"
    assert report["provenance"]["errors"] == []


def test_validator_detects_hash_mismatch_in_direct_public_link(tmp_path: Path):
    root = tmp_path / "release"
    root.mkdir()
    source_dir = root / "data" / "raw" / "city_topology_v01"
    source_dir.mkdir(parents=True)
    source = source_dir / "city_master_2024.csv"
    source.write_text("city_code\n1\n", encoding="utf-8", newline="\n")

    source_manifest = source_dir / "source_manifest.csv"
    source_manifest.write_text(
        "source_id,dataset,publisher,source_url,data_year,accessed_on,evidence_grade,local_path,origin_type,parent_source_ids,provenance_note,sha256,link_status,repository_source_id\n"
        "CITY-REGISTRY-SNAPSHOT-V01,Frozen city registry,Project-local,project://city,2024,2026-07-31,D_model_proxy,data/raw/city_topology_v01/city_master_2024.csv,project,not_applicable,public carrier,"
        + "0" * 64
        + ",direct_public_carrier,city-master-2024-v01\n",
        encoding="utf-8",
        newline="\n",
    )
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    assert expected != "0" * 64

    report = validate_repository_provenance(root)

    assert report["status"] == "FAIL"
    assert report["hash_mismatches"] == ["CITY-REGISTRY-SNAPSHOT-V01"]


def test_validator_never_reads_historical_metadata_path(tmp_path: Path):
    root = tmp_path / "release"
    source_dir = root / "data" / "raw" / "city_topology_v01"
    source_dir.mkdir(parents=True)
    source_manifest = source_dir / "source_manifest.csv"
    source_manifest.write_text(
        "source_id,dataset,publisher,source_url,data_year,accessed_on,evidence_grade,local_path,origin_type,parent_source_ids,provenance_note,sha256,link_status,repository_source_id\n"
        "LEGACY-ONLY,Legacy input,Project-local,project://legacy,2024,2026-07-31,D_model_proxy,historical://not-present.csv,legacy,not_applicable,historical metadata only,not_applicable,historical_metadata_only,not_applicable\n",
        encoding="utf-8",
        newline="\n",
    )

    report = validate_repository_provenance(root)

    assert report["status"] == "PASS"
    assert report["errors"] == []
    assert report["historical_metadata_only_count"] == 1
