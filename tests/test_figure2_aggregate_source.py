from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "author_derived" / "figure2_aggregate_source.csv"
DICTIONARY = ROOT / "data" / "dictionaries" / "figure2_aggregate_source.md"

REQUIRED_COLUMNS = {
    "panel",
    "record_type",
    "scenario",
    "tier",
    "year",
    "metric",
    "value",
    "unit",
    "source_boundary",
}
EXPECTED_PANEL_COUNTS = {"a": 67, "b": 24, "c": 24, "d": 12, "e": 1, "f": 33, "g": 3, "h": 9}
RESTRICTED_TOKENS = (
    "node_id",
    "edge_id",
    "segment_id",
    "facility",
    "station_name",
    "latitude",
    "longitude",
    "coordinate",
    "source_path",
    "pipeline_node",
    "refinery_city",
)


def _rows() -> list[dict[str, str]]:
    with SOURCE.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_figure2_carrier_schema_and_panel_counts():
    rows = _rows()
    assert rows
    assert REQUIRED_COLUMNS <= set(rows[0])
    assert Counter(row["panel"] for row in rows) == EXPECTED_PANEL_COUNTS
    for row in rows:
        assert all(row[column].strip() for column in REQUIRED_COLUMNS)


def test_figure2_carrier_has_no_restricted_identifiers_or_machine_paths():
    text = SOURCE.read_text(encoding="utf-8").casefold()
    assert not any(token in text for token in RESTRICTED_TOKENS)
    assert not re.search(r"[a-z]:[\\/]", text)
    assert not re.search(r"(?:^|[\s,])/(?:[a-z0-9._-]+/)+", text)


def test_figure2_panel_e_is_explicitly_unavailable():
    rows = [row for row in _rows() if row["panel"] == "e"]
    assert len(rows) == 1
    row = rows[0]
    assert row["record_type"] == "status"
    assert row["value"] == "unavailable"
    assert "restricted-map-not-released" in row["source_boundary"]


def test_figure2_headline_aggregates_are_released_without_map_payload():
    rows = _rows()

    def find(**criteria: str) -> dict[str, str]:
        return next(row for row in rows if all(row[key] == value for key, value in criteria.items()))

    assert abs(float(find(panel="b", scenario="S5", metric="quantity_shortage_pct")["value"]) - 12.612401) < 1e-6
    assert abs(float(find(panel="a", scenario="S5", year="2060", metric="dynamic_demand_mt")["value"]) - 72.5) < 1e-9
    assert abs(float(find(panel="c", scenario="S2", metric="topology_access_residual_pct")["value"]) - 90.656370) < 1e-6
    assert abs(float(find(panel="d", scenario="S5", metric="direction_relaxation_gain_10kt")["value"]) - 482.2846) < 1e-6
    assert abs(float(find(panel="f", variant="baseline", scenario="S1-S8", metric="unserved_pct")["value"]) - 73.788504) < 1e-6
    assert abs(float(find(panel="g", scenario="S1-S8", metric="pipeline_service_pct")["value"]) - 47.747761) < 1e-6
    assert abs(float(find(panel="h", scenario="S1-S8", metric="interaction_effect_pp")["value"]) - 32.142449) < 1e-6


def test_figure2_dictionary_and_panel_map_pair_the_carrier():
    dictionary = DICTIONARY.read_text(encoding="utf-8")
    for column in sorted(REQUIRED_COLUMNS | {"variant"}):
        assert f"| {column} |" in dictionary
    assert "upstream" in dictionary.casefold()
    assert "fig03_dynamic_v08_source_data.csv" in dictionary
    assert "not the current Figure 2 source file" in dictionary
    assert "restricted-map-not-released" in dictionary

    with (ROOT / "figures" / "panel_map.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    figure2 = [row for row in rows if row["figure"] == "Figure 2"]
    assert figure2 == [
        {
            "figure": "Figure 2",
            "panel": "a-d,f-h",
            "status": "aggregate-only",
            "source_data": "data/author_derived/figure2_aggregate_source.csv",
            "dictionary": "data/dictionaries/figure2_aggregate_source.md",
            "reason": "safe aggregate carrier; panel e restricted-map-not-released",
        }
    ]
