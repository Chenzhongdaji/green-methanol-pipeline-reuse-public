from __future__ import annotations

import json
import hashlib
import math
from pathlib import Path

import pandas as pd
import pytest

from green_methanol_release.model import network as network_module
from green_methanol_release.model.analysis import run_dynamic_analysis
from green_methanol_release.model.config import load_config
from green_methanol_release.model.demand import preprocess_demand
from green_methanol_release.model.analysis import load_analysis_outputs
from green_methanol_release.model.network import load_network_outputs
from green_methanol_release.model.io import write_csv
from green_methanol_release.model.workflow import (
    MODEL_OUTPUT_DIR,
    run_model_chain,
    run_model_stage,
)


ROOT = Path(__file__).resolve().parents[1]


def test_model_csv_writer_canonicalizes_platform_ulp_noise(tmp_path: Path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    value = 626.2609051227721

    write_csv(pd.DataFrame({"value": [value]}), first)
    write_csv(pd.DataFrame({"value": [math.nextafter(value, math.inf)]}), second)

    assert first.read_bytes() == second.read_bytes()
    assert first.read_text(encoding="utf-8") == "value\n626.2609051228\n"


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
        pd.testing.assert_frame_equal(left, right, check_dtype=True, check_exact=True)
    assert first.audit == second.audit


def test_write_through_chain_matches_registered_stage_carriers():
    """The convenience chain must use the same persisted carriers as full mode."""

    result = run_model_chain(ROOT, write_outputs=True)
    run_model_stage(ROOT, "demand_preprocessing")
    run_model_stage(ROOT, "directed_network_flow")
    run_model_stage(ROOT, "dynamic_analysis")
    persisted_network = load_network_outputs(ROOT)
    persisted_analysis = load_analysis_outputs(ROOT)

    for left, right in (
        (result.network.summary, persisted_network.summary),
        (result.network.service, persisted_network.service),
        (result.analysis.summary, persisted_analysis.summary),
        (result.analysis.regional_accounts, persisted_analysis.regional_accounts),
        (result.analysis.figure_04_source, persisted_analysis.figure_04_source),
        (result.analysis.figure_05_source, persisted_analysis.figure_05_source),
    ):
        pd.testing.assert_frame_equal(left, right, check_dtype=True, check_exact=True)


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


def test_network_capacity_uses_same_pipeline_task_and_haversine_distance():
    segments = network_module._read_segments(ROOT)
    tasks = network_module._read_segment_tasks(ROOT, segments)
    task = tasks[(tasks["segment_id"] == "S012") & (tasks["year"] == 2025)].iloc[0]
    assert task["same_pipeline_task_10kt"] == pytest.approx(563.0523474025721)
    raw_tasks = pd.read_csv(
        ROOT / "data" / "raw" / "pipeline" / "segment_transport_task_pipeline_adjusted_long.csv",
        encoding="utf-8-sig",
    )
    raw_row = raw_tasks[(raw_tasks.iloc[:, 0] == "S012") & (raw_tasks.iloc[:, 4] == 2025)].iloc[0]
    assert float(raw_row.iloc[10]) != pytest.approx(float(raw_row.iloc[6]))

    result = run_model_chain(ROOT, write_outputs=False)
    catalog = result.network.edge_catalog
    known = catalog[(catalog["segment_id"] == "S012") & (catalog["year"] == 2025)].iloc[0]
    assert known["capacity_basis"] == "同管道运输任务_万吨"
    assert known["capacity_10kt"] == pytest.approx(1000.0 - 563.0523474025721)
    segment = segments[segments["segment_id"] == "S012"].iloc[0]
    assert known["distance_km"] == pytest.approx(
        network_module.haversine_km(
            segment["from_lon"],
            segment["from_lat"],
            segment["to_lon"],
            segment["to_lat"],
        )
    )
    assert known["distance_km"] > 1.0


def test_base_segment_distance_inherits_v08_one_km_lower_bound():
    segments = network_module._read_segments(ROOT)
    coincident = segments[segments["segment_id"] == "S019"].iloc[0]
    assert network_module.haversine_km(
        coincident["from_lon"],
        coincident["from_lat"],
        coincident["to_lon"],
        coincident["to_lat"],
    ) == pytest.approx(0.0)
    assert coincident["distance_km"] == pytest.approx(1.0)

    result = run_model_chain(ROOT, write_outputs=False)
    assert result.network.edge_catalog["distance_km"].min() >= 1.0
    known = result.network.edge_catalog[
        (result.network.edge_catalog["segment_id"] == "S019")
        & (result.network.edge_catalog["year"] == 2025)
    ].iloc[0]
    assert known["distance_km"] == pytest.approx(1.0)


def test_model_config_exposes_capacity_basis_without_active_emission_control():
    config = load_config(ROOT)
    assert config.capacity_basis == "same_pipeline_task_10kt"
    assert not hasattr(config, "transport_emission_per_km")
    assert "transport_emission_per_km" not in (
        ROOT / "config" / "model_parameters_v01.csv"
    ).read_text(encoding="utf-8")


def test_candidate_links_are_figure5_only_and_unknown_nodes_fail_fast():
    assert "candidate_links" not in network_module.NETWORK_INPUTS
    assert "selected_plans" not in network_module.NETWORK_INPUTS
    result = run_model_chain(ROOT, write_outputs=False)
    assert result.network.audit["network_variant"] == "base"
    assert result.network.audit["candidate_scope"].startswith("Figure-5 sensitivity only")
    assert not result.network.edge_flows["segment_id"].astype(str).str.startswith("C").any()
    assert (result.network.summary["connector_count"] == 0).all()
    with pytest.raises(ValueError, match="unknown public node"):
        network_module._read_candidate_links(
            ROOT,
            {"N001": "public"},
            {"N001": (87.0, 43.0)},
        )


def test_network_audit_hashes_declared_stage_inputs(tmp_path: Path):
    result = run_model_stage(ROOT, "directed_network_flow", output_root=tmp_path)
    expected = {
        *(f"demand::{path}" for path in network_module.DEMAND_OUTPUTS.values()),
        *(f"network::{path}" for path in network_module.NETWORK_INPUTS.values()),
    }
    assert set(result.audit["input_hashes"]) == expected
    assert all(len(value) == 64 for value in result.audit["input_hashes"].values())


def test_analysis_consumes_stage_carriers_without_recomputing_demand(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("analysis must consume stage carriers")

    monkeypatch.setattr("green_methanol_release.model.analysis.preprocess_demand", fail)
    demand = preprocess_demand(ROOT)
    network = network_module.run_network(ROOT, demand)
    result = run_dynamic_analysis(ROOT, demand, network)
    assert result.audit["status"] == "PASS"
