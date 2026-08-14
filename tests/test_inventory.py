from pathlib import Path

from green_methanol_release.inventory import validate_inventory


ROOT = Path(__file__).resolve().parents[1]


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
