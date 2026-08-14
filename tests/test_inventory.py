import csv
import shutil
from pathlib import Path

import pytest

from green_methanol_release.inventory import (
    CONTROLLED_FIELDS,
    PUBLIC_SOURCE_FIELDS,
    load_public_sources,
    validate_inventory,
)


ROOT = Path(__file__).resolve().parents[1]


def _sandbox_inventory(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    for name in ("public_sources.csv", "controlled_inputs_metadata.csv"):
        shutil.copy2(ROOT / "data" / name, data / name)
    return tmp_path


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_rows(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_public_source_register_is_complete_and_non_redistributive():
    result = validate_inventory(ROOT)
    assert result["public_source_rows"] >= 37
    assert result["engineering_source_rows"] == 8


def test_controlled_register_has_exact_approved_families():
    result = validate_inventory(ROOT)
    assert result["controlled_rows"] == 4
    assert result["zero_hash_rows"] == 0


def test_third_party_sources_are_not_cc_by_relicensed():
    result = validate_inventory(ROOT)
    assert result["third_party_cc_by_rows"] == 0


def test_connector_scenario_base_locator_matches_reviewed_source():
    row = next(
        row
        for row in load_public_sources(ROOT / "data" / "public_sources.csv")
        if row["source_id"] == "CONNECTOR-SCENARIO-BASE"
    )
    assert row["stable_url_or_doi"] == (
        "https://sthjt.shaanxi.gov.cn/xxgk/fdnr/zcwj/shpf/"
        "202602/t20260224_3614544.html"
    )


@pytest.mark.parametrize("hash_note", ["reason without marker", "hash_unavailable", "hash_unavailable:   "])
def test_empty_hash_requires_marker_and_non_empty_reason(tmp_path: Path, hash_note: str):
    root = _sandbox_inventory(tmp_path)
    path = root / "data" / "controlled_inputs_metadata.csv"
    rows = _read_rows(path)
    rows[0]["sha256"] = ""
    rows[0]["hash_note"] = hash_note
    _write_rows(path, CONTROLLED_FIELDS, rows)

    with pytest.raises(ValueError, match="hash_unavailable"):
        validate_inventory(root)


def test_real_digest_requires_empty_hash_note(tmp_path: Path):
    root = _sandbox_inventory(tmp_path)
    path = root / "data" / "controlled_inputs_metadata.csv"
    rows = _read_rows(path)
    rows[0]["sha256"] = "a" * 64
    rows[0]["hash_note"] = "retained note"
    _write_rows(path, CONTROLLED_FIELDS, rows)

    with pytest.raises(ValueError, match="hash_note"):
        validate_inventory(root)


def test_cc_by_separator_variants_are_rejected_for_third_party_rows(tmp_path: Path):
    root = _sandbox_inventory(tmp_path)
    path = root / "data" / "public_sources.csv"
    rows = _read_rows(path)
    rows[0]["licence_or_rights_status"] = "CC-BY-4.0"
    _write_rows(path, PUBLIC_SOURCE_FIELDS, rows)

    with pytest.raises(ValueError, match="third-party"):
        validate_inventory(root)


def test_author_derived_source_type_alias_cannot_claim_repository_cc_by(tmp_path: Path):
    root = _sandbox_inventory(tmp_path)
    path = root / "data" / "public_sources.csv"
    rows = _read_rows(path)
    rows[0]["source_type"] = "author-derived aggregate"
    rows[0]["licence_or_rights_status"] = "CC BY 4.0"
    _write_rows(path, PUBLIC_SOURCE_FIELDS, rows)

    with pytest.raises(ValueError, match="third-party"):
        validate_inventory(root)


def test_inventory_rejects_extra_columns(tmp_path: Path):
    root = _sandbox_inventory(tmp_path)
    path = root / "data" / "public_sources.csv"
    rows = _read_rows(path)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(*PUBLIC_SOURCE_FIELDS, "extra"),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "extra": "unexpected"})

    with pytest.raises(ValueError, match="columns"):
        validate_inventory(root)


def test_inventory_rejects_duplicate_identifiers(tmp_path: Path):
    root = _sandbox_inventory(tmp_path)
    path = root / "data" / "public_sources.csv"
    rows = _read_rows(path)
    rows[1]["source_id"] = rows[0]["source_id"]
    _write_rows(path, PUBLIC_SOURCE_FIELDS, rows)

    with pytest.raises(ValueError, match="duplicate"):
        validate_inventory(root)


def test_inventory_rejects_non_lowercase_digest(tmp_path: Path):
    root = _sandbox_inventory(tmp_path)
    path = root / "data" / "controlled_inputs_metadata.csv"
    rows = _read_rows(path)
    rows[0]["sha256"] = "A" * 64
    rows[0]["hash_note"] = ""
    _write_rows(path, CONTROLLED_FIELDS, rows)

    with pytest.raises(ValueError, match="64 lowercase hexadecimal"):
        validate_inventory(root)
