from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pandas as pd
import pytest

from green_methanol_release.model.workflow import (
    MODEL_OUTPUT_DIR,
    run_model_chain,
    run_model_stage,
)


ROOT = Path(__file__).resolve().parents[1]


def test_public_model_chain_closes_demand_flow_and_analysis_accounts():
    result = run_model_chain(ROOT, write_outputs=False)

    assert result.audit["status"] == "PASS"
    assert result.audit["stages"] == {
        "demand_preprocessing": "PASS",
        "directed_network_flow": "PASS",
        "dynamic_analysis": "PASS",
        "figure_source_regeneration": "PASS",
    }
    assert not result.demand.nodes.empty
    assert not result.network.summary.empty
    assert not result.network.edge_flows.empty

    demand_totals = result.demand.nodes.groupby(
        ["scenario", "tier", "year"], sort=True
    )["demand_10kt"].sum()
    network_totals = result.network.summary.set_index(
        ["scenario", "tier", "year"]
    )["demand_10kt"]
    pd.testing.assert_series_equal(
        demand_totals.sort_index(), network_totals.sort_index(), check_names=False
    )
    assert (result.network.edge_flows["flow_10kt"] >= 0).all()
    assert (
        result.network.edge_flows["flow_10kt"]
        <= result.network.edge_flows["capacity_10kt"] + 1e-9
    ).all()

    regional = result.analysis.regional_accounts
    assert not regional.empty
    assert (
        regional["demand_methanol_10kt"]
        - regional["served_methanol_10kt"]
        - regional["unserved_methanol_10kt"]
    ).abs().max() < 1e-8
    assert (
        regional["served_methanol_10kt"]
        - regional["local_direct_methanol_10kt"]
        - regional["pipeline_served_methanol_10kt"]
    ).abs().max() < 1e-8


def test_public_model_chain_is_deterministic_under_repeated_in_memory_runs():
    first = run_model_chain(ROOT, write_outputs=False)
    second = run_model_chain(ROOT, write_outputs=False)

    for left, right in (
        (first.demand.nodes, second.demand.nodes),
        (first.network.summary, second.network.summary),
        (first.network.edge_flows, second.network.edge_flows),
        (first.analysis.regional_accounts, second.analysis.regional_accounts),
        (first.analysis.figure_04_source, second.analysis.figure_04_source),
        (first.analysis.figure_05_source, second.analysis.figure_05_source),
    ):
        pd.testing.assert_frame_equal(left, right, check_dtype=True)
    assert first.audit == second.audit


def test_model_stage_writes_release_relative_outputs_only(tmp_path: Path):
    result = run_model_stage(ROOT, "demand_preprocessing", output_root=tmp_path)

    assert result.audit["status"] == "PASS"
    assert result.output_paths
    for path in result.output_paths:
        assert not Path(path).is_absolute() or str(path).startswith(str(tmp_path))
        assert "ROOT.parent" not in str(path)
        assert Path(path).is_file()
    assert (tmp_path / MODEL_OUTPUT_DIR / "demand_nodes.csv").is_file()


def test_external_stage_audit_hashes_the_external_artifact(tmp_path: Path):
    result = run_model_stage(ROOT, "demand_preprocessing", output_root=tmp_path)

    relative = f"{MODEL_OUTPUT_DIR}/demand_nodes.csv"
    artifact = tmp_path / relative
    expected = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert result.audit["output_hashes"][relative] == expected


def test_model_chain_outputs_have_no_machine_absolute_paths_or_private_markers():
    result = run_model_chain(ROOT, write_outputs=False)
    payload = json.dumps(result.audit, ensure_ascii=False, sort_keys=True)
    assert "NOT_REPRODUCED" not in payload
    assert "ROOT.parent" not in payload
    assert "\\\\" not in payload
    private_markers = (
        "E:" + chr(92),
        "C:" + chr(92),
        "/" + "home" + "/",
        "/" + "Users" + "/",
        "/" + "root" + "/",
    )
    assert not any(token in payload for token in private_markers)


def test_model_source_tables_match_figure_contracts():
    result = run_model_chain(ROOT, write_outputs=False)
    assert list(result.analysis.figure_04_source.columns) == [
        "scenario",
        "tier",
        "year",
        "region",
        "demand_methanol_10kt",
        "local_direct_methanol_10kt",
        "pipeline_served_methanol_10kt",
        "served_methanol_10kt",
        "unserved_methanol_10kt",
        "demand_met_pct",
        "pipeline_share_pct",
    ]
    assert list(result.analysis.figure_05_source.columns) == [
        "panel",
        "scenario",
        "year",
        "metric",
        "value",
        "unit",
        "source_type",
        "style",
        "marker",
        "capacity_relaxation_gain_mt_y",
        "connector_gain_mt_y",
        "capacity_reaches_connector",
    ]
    assert set(result.analysis.figure_05_source["panel"]) == {"c"}


def test_model_carriers_are_hashable_and_have_schema_metadata():
    result = run_model_chain(ROOT, write_outputs=True)

    assert result.audit["input_hashes"]
    assert result.audit["output_hashes"]
    assert all(len(value) == 64 for value in result.audit["input_hashes"].values())
    assert all(len(value) == 64 for value in result.audit["output_hashes"].values())
    schema = result.audit["schema"]
    assert schema["demand_nodes"]
    assert schema["network_edge_flows"]
    assert schema["figure_04_source"]
    assert schema["figure_05_source"]


@pytest.mark.parametrize("relative", [
    "scripts/model/preprocess_demand.py",
    "scripts/model/run_network.py",
    "scripts/model/build_analysis.py",
    "scripts/model/build_figure_04.py",
    "scripts/model/build_figure_05.py",
])
def test_model_cli_scripts_are_present(relative: str):
    assert (ROOT / relative).is_file()
