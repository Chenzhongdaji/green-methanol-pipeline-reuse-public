"""Dynamic account analysis and model-derived Figure 4/5 source tables."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

import pandas as pd

from .config import YEARS, SCENARIOS, TIERS, load_config
from .demand import (
    DEMAND_OUTPUTS,
    DemandResult,
    load_demand_outputs,
    preprocess_demand,
)
from .io import (
    finalize_stage_audit,
    hashes_for_paths,
    read_csv,
    sorted_frame,
    verify_persisted_stage,
    write_csv,
    write_json,
)
from .network import (
    CANDIDATE_INPUTS,
    NETWORK_OUTPUTS,
    NetworkResult,
    NetworkTopology,
    _read_candidate_links,
    load_network_outputs,
    run_network,
)


ANALYSIS_INPUTS = {
    "demand_nodes": DEMAND_OUTPUTS["nodes"],
    "demand_totals": DEMAND_OUTPUTS["totals"],
    "demand_supply": DEMAND_OUTPUTS["supply"],
    "demand_components": DEMAND_OUTPUTS["components"],
    "demand_audit": DEMAND_OUTPUTS["audit"],
    "network_summary": NETWORK_OUTPUTS["summary"],
    "network_edge_flows": NETWORK_OUTPUTS["edge_flows"],
    "network_service": NETWORK_OUTPUTS["service"],
    "network_edge_catalog": NETWORK_OUTPUTS["edge_catalog"],
    "network_node_catalog": NETWORK_OUTPUTS["node_catalog"],
    "network_audit": NETWORK_OUTPUTS["audit"],
    "candidate_links": CANDIDATE_INPUTS["candidate_links"],
    "selected_plans": CANDIDATE_INPUTS["selected_plans"],
    "parameters": "config/model_parameters_v01.csv",
}
ANALYSIS_OUTPUTS = {
    "summary": "data/processed/model_v01/analysis_summary.csv",
    "regional_accounts": "data/processed/model_v01/regional_accounts.csv",
    "figure_04_source": "data/processed/model_v01/figure_04_source.csv",
    "figure_05_source": "data/processed/model_v01/figure_05_source.csv",
    "audit": "data/processed/model_v01/dynamic_analysis_audit.json",
}
ANALYSIS_FIGURE_SOURCES = {
    "figure_04": ANALYSIS_OUTPUTS["figure_04_source"],
    "figure_05": ANALYSIS_OUTPUTS["figure_05_source"],
}
ANALYSIS_SUMMARY_COLUMNS = (
    "scenario",
    "tier",
    "year",
    "demand_10kt",
    "supply_10kt",
    "local_direct_10kt",
    "pipeline_served_10kt",
    "served_10kt",
    "unserved_10kt",
    "demand_met_pct",
    "pipeline_delivery_share_pct",
    "pipeline_tonne_km",
    "average_pipeline_distance_km",
    "edges_used",
    "max_edge_util_pct",
    "min_cost_objective",
)
ANALYSIS_REGIONAL_COLUMNS = (
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
)
ANALYSIS_FIGURE_04_COLUMNS = ANALYSIS_REGIONAL_COLUMNS
ANALYSIS_FIGURE_05_COLUMNS = (
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
)

REGION_BY_PROVINCE = {
    "北京": "NC",
    "天津": "NC",
    "河北": "NC",
    "山西": "NC",
    "内蒙古": "NC",
    "辽宁": "NE",
    "吉林": "NE",
    "黑龙江": "NE",
    "上海": "EC",
    "江苏": "EC",
    "浙江": "EC",
    "安徽": "EC",
    "福建": "EC",
    "江西": "EC",
    "山东": "EC",
    "河南": "CC",
    "湖北": "CC",
    "湖南": "CC",
    "广东": "SC",
    "广西": "SC",
    "海南": "SC",
    "重庆": "SW",
    "四川": "SW",
    "贵州": "SW",
    "云南": "SW",
    "西藏": "SW",
    "陕西": "NW",
    "甘肃": "NW",
    "青海": "NW",
    "宁夏": "NW",
    "新疆": "NW",
}
REGIONS = ("NC", "NE", "EC", "CC", "SC", "SW", "NW")


@dataclass(frozen=True)
class AnalysisResult:
    summary: pd.DataFrame
    regional_accounts: pd.DataFrame
    figure_04_source: pd.DataFrame
    figure_05_source: pd.DataFrame
    audit: dict[str, Any]
    input_hashes: dict[str, str]


def _regional_accounts(network: NetworkResult) -> pd.DataFrame:
    service = network.service.copy()
    service["region"] = service["province_key"].map(REGION_BY_PROVINCE)
    if service["region"].isna().any():
        missing = sorted(service.loc[service["region"].isna(), "province_key"].unique())
        raise ValueError(f"regional map is missing provinces: {missing}")
    grouped = service.groupby(["scenario", "tier", "year", "region"], sort=True)[
        [
            "demand_10kt",
            "local_direct_10kt",
            "pipeline_served_10kt",
            "served_10kt",
            "unserved_10kt",
        ]
    ].sum()
    rows: list[dict[str, Any]] = []
    scenario_values = sorted(service["scenario"].unique(), key=lambda value: int(str(value)[1:]))
    for scenario in scenario_values:
        for tier in ("low", "mid", "high"):
            for year in YEARS:
                for region in REGIONS:
                    key = (scenario, tier, year, region)
                    if key in grouped.index:
                        values = grouped.loc[key]
                    else:
                        values = {field: 0.0 for field in ("demand_10kt", "local_direct_10kt", "pipeline_served_10kt", "served_10kt", "unserved_10kt")}
                    demand = float(values["demand_10kt"])
                    served = float(values["served_10kt"])
                    local = float(values["local_direct_10kt"])
                    pipeline = float(values["pipeline_served_10kt"])
                    unserved = float(values["unserved_10kt"])
                    rows.append(
                        {
                            "scenario": scenario,
                            "tier": tier,
                            "year": year,
                            "region": region,
                            "demand_methanol_10kt": demand,
                            "local_direct_methanol_10kt": local,
                            "pipeline_served_methanol_10kt": pipeline,
                            "served_methanol_10kt": served,
                            "unserved_methanol_10kt": unserved,
                            "demand_met_pct": 100.0 * served / demand if demand else 0.0,
                            "pipeline_share_pct": 100.0 * pipeline / served if served else 0.0,
                        }
                    )
    return sorted_frame(pd.DataFrame(rows), ("scenario", "tier", "year", "region"))


def _figure_04_source(regional: pd.DataFrame) -> pd.DataFrame:
    source = regional[regional["tier"].eq("mid") & regional["year"].eq(2060)].copy()
    if len(source) != len(SCENARIOS) * len(REGIONS):
        raise ValueError("Figure 4 source must contain every scenario and region at mid/2060")
    return sorted_frame(
        source[
            [
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
        ],
        ("scenario", "tier", "year", "region"),
    )


def _figure_05_source(
    root: Path,
    demand: DemandResult,
    baseline: NetworkResult,
    config_factor: float,
) -> pd.DataFrame:
    scenarios = tuple(sorted(baseline.summary["scenario"].unique(), key=lambda value: int(str(value)[1:])))
    if baseline.node_catalog is None or baseline.topology is None:
        raise ValueError("network result is missing the public base topology")
    node_provinces = dict(
        zip(
            baseline.node_catalog["node_id"],
            baseline.node_catalog["province_key"],
            strict=True,
        )
    )
    node_coordinates = dict(
        zip(
            baseline.node_catalog["node_id"],
            zip(
                baseline.node_catalog["longitude"],
                baseline.node_catalog["latitude"],
                strict=True,
            ),
            strict=True,
        )
    )
    relaxed = run_network(
        root,
        demand,
        capacity_factor=config_factor,
        scenarios=scenarios,
        topology=baseline.topology,
    )
    candidate_map, selected = _read_candidate_links(root, node_provinces, node_coordinates)
    connector_specs = {
        scenario: [candidate_map[selected[scenario]]]
        for scenario in scenarios
        if scenario in selected and selected[scenario] in candidate_map
    }
    connector = run_network(
        root,
        demand,
        connector_by_scenario=connector_specs,
        scenarios=scenarios,
        topology=baseline.topology,
    )
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        base_row = baseline.summary[
            baseline.summary["scenario"].eq(scenario)
            & baseline.summary["tier"].eq("mid")
            & baseline.summary["year"].eq(2060)
        ].iloc[0]
        relaxed_row = relaxed.summary[
            relaxed.summary["scenario"].eq(scenario)
            & relaxed.summary["tier"].eq("mid")
            & relaxed.summary["year"].eq(2060)
        ].iloc[0]
        connector_row = connector.summary[
            connector.summary["scenario"].eq(scenario)
            & connector.summary["tier"].eq("mid")
            & connector.summary["year"].eq(2060)
        ].iloc[0]
        base_served = float(base_row["served_10kt"])
        capacity_gain = max(0.0, float(relaxed_row["served_10kt"]) - base_served) / 100.0
        connector_gain = max(0.0, float(connector_row["served_10kt"]) - base_served) / 100.0
        reaches = capacity_gain >= connector_gain - 1e-12
        for metric, value, style, marker in (
            ("capacity_relaxation_gain_mt_y", capacity_gain, "dumbbell_endpoint", "hollow_gray_circle"),
            ("fixed_connector_gain_mt_y", connector_gain, "dumbbell_endpoint", "orange_square"),
        ):
            rows.append(
                {
                    "panel": "c",
                    "scenario": scenario,
                    "year": 2060,
                    "metric": metric,
                    "value": value,
                    "unit": "Mt/y",
                    "source_type": "public_directed_model_candidate_sensitivity",
                    "style": style,
                    "marker": marker,
                    "capacity_relaxation_gain_mt_y": capacity_gain,
                    "connector_gain_mt_y": connector_gain,
                    "capacity_reaches_connector": reaches,
                }
            )
    return sorted_frame(pd.DataFrame(rows), ("scenario", "year", "metric"))


def _analysis_summary(network: NetworkResult) -> pd.DataFrame:
    summary = network.summary.copy()
    summary["average_pipeline_distance_km"] = summary.apply(
        lambda row: float(row["pipeline_tonne_km"]) / (float(row["pipeline_served_10kt"]) * 10000.0)
        if float(row["pipeline_served_10kt"]) > 0
        else 0.0,
        axis=1,
    )
    summary["pipeline_delivery_share_pct"] = summary.apply(
        lambda row: 100.0 * float(row["pipeline_served_10kt"]) / float(row["demand_10kt"])
        if float(row["demand_10kt"]) > 0
        else 0.0,
        axis=1,
    )
    return sorted_frame(
        summary[
            [
                "scenario",
                "tier",
                "year",
                "demand_10kt",
                "supply_10kt",
                "local_direct_10kt",
                "pipeline_served_10kt",
                "served_10kt",
                "unserved_10kt",
                "demand_met_pct",
                "pipeline_delivery_share_pct",
                "pipeline_tonne_km",
                "average_pipeline_distance_km",
                "edges_used",
                "max_edge_util_pct",
                "min_cost_objective",
            ]
        ],
        ("scenario", "tier", "year"),
    )


def run_dynamic_analysis(
    root: Path,
    demand: DemandResult | None = None,
    network: NetworkResult | None = None,
) -> AnalysisResult:
    """Build dynamic regional/logistics accounts and model-derived Figure 4/5 sources."""

    root = Path(root).resolve()
    config = load_config(root)
    demand_result = preprocess_demand(root) if demand is None else demand
    network_result = run_network(root, demand_result) if network is None else network
    if network_result.topology is None:
        raise ValueError("dynamic analysis requires a reusable public base topology")
    regional = _regional_accounts(network_result)
    figure_04 = _figure_04_source(regional)
    figure_05 = _figure_05_source(root, demand_result, network_result, config.capacity_relaxation_factor)
    summary = _analysis_summary(network_result)
    if (regional["demand_methanol_10kt"] - regional["served_methanol_10kt"] - regional["unserved_methanol_10kt"]).abs().max() > 1e-8:
        raise RuntimeError("regional demand accounts do not close")
    analysis_paths = sorted(set(ANALYSIS_INPUTS.values()))
    if all((root / Path(*relative.split("/"))).is_file() for relative in analysis_paths):
        input_hashes = hashes_for_paths(root, analysis_paths)
    else:
        # In-memory composition is used by ``run_model_chain`` before stage
        # carriers are written.  Preserve provenance without forcing an
        # in-memory run to depend on stale or absent downstream files.
        input_hashes = {
            **demand_result.input_hashes,
            **network_result.input_hashes,
            **hashes_for_paths(root, CANDIDATE_INPUTS.values()),
            "config/model_parameters_v01.csv": hashes_for_paths(
                root, ("config/model_parameters_v01.csv",)
            )["config/model_parameters_v01.csv"],
        }
    candidate_hashes = hashes_for_paths(root, CANDIDATE_INPUTS.values())
    audit = {
        "status": "PASS",
        "stage": "dynamic_analysis",
        "input_paths": sorted(set(ANALYSIS_INPUTS.values())),
        "input_hashes": input_hashes,
        "schema": {
            "analysis_summary": list(summary.columns),
            "regional_accounts": list(regional.columns),
            "figure_04_source": list(figure_04.columns),
            "figure_05_source": list(figure_05.columns),
        },
        "rows": {
            "analysis_summary": int(len(summary)),
            "regional_accounts": int(len(regional)),
            "figure_04_source": int(len(figure_04)),
            "figure_05_source": int(len(figure_05)),
        },
        "counterfactuals": {
            "capacity_relaxation_factor": config.capacity_relaxation_factor,
            "connector_selection": "first public candidate in best_two_link_plans per scenario",
            "candidate_scope": "Figure-5 sensitivity only; candidates are not base-network edges",
            "candidate_input_hashes": candidate_hashes,
        },
        "transport_emission": "reserved_not_implemented",
        "boundary": "regional and logistics metrics are model-derived accounts; they are not observations or segment qualification decisions; legacy pressure/cost details are omitted",
    }
    return AnalysisResult(summary, regional, figure_04, figure_05, audit, input_hashes)


def write_analysis_outputs(result: AnalysisResult, root: Path) -> list[str]:
    """Persist analysis tables and the model-derived Figure 4/5 source carriers."""

    output_dir = Path(root).resolve() / "data" / "processed" / "model_v01"
    write_csv(result.summary, output_dir / "analysis_summary.csv")
    write_csv(result.regional_accounts, output_dir / "regional_accounts.csv")
    write_csv(result.figure_04_source, output_dir / "figure_04_source.csv")
    write_csv(result.figure_05_source, output_dir / "figure_05_source.csv")
    output_paths = [
        "data/processed/model_v01/analysis_summary.csv",
        "data/processed/model_v01/regional_accounts.csv",
        "data/processed/model_v01/figure_04_source.csv",
        "data/processed/model_v01/figure_05_source.csv",
        "data/processed/model_v01/dynamic_analysis_audit.json",
    ]
    audit = finalize_stage_audit(
        result.audit,
        root,
        output_paths,
        ANALYSIS_OUTPUTS["audit"],
    )
    write_json(audit, output_dir / "dynamic_analysis_audit.json")
    return output_paths


def load_analysis_outputs(root: Path) -> AnalysisResult:
    """Load only analysis source carriers for the model-figure stages."""

    payload = verify_persisted_stage(
        root,
        ANALYSIS_OUTPUTS["audit"],
        ANALYSIS_OUTPUTS.values(),
        "dynamic_analysis",
    )
    summary = read_csv(root, ANALYSIS_OUTPUTS["summary"], ANALYSIS_SUMMARY_COLUMNS)
    regional = read_csv(root, ANALYSIS_OUTPUTS["regional_accounts"], ANALYSIS_REGIONAL_COLUMNS)
    figure_04 = read_csv(root, ANALYSIS_OUTPUTS["figure_04_source"], ANALYSIS_FIGURE_04_COLUMNS)
    figure_05 = read_csv(root, ANALYSIS_OUTPUTS["figure_05_source"], ANALYSIS_FIGURE_05_COLUMNS)
    input_hashes = payload.get("input_hashes")
    if not isinstance(input_hashes, dict) or not input_hashes:
        raise ValueError("analysis-stage audit is missing input hashes")
    return AnalysisResult(
        summary,
        regional,
        figure_04,
        figure_05,
        payload,
        {str(key): str(value) for key, value in input_hashes.items()},
    )


__all__ = [
    "ANALYSIS_FIGURE_SOURCES",
    "ANALYSIS_FIGURE_04_COLUMNS",
    "ANALYSIS_FIGURE_05_COLUMNS",
    "ANALYSIS_INPUTS",
    "ANALYSIS_OUTPUTS",
    "ANALYSIS_REGIONAL_COLUMNS",
    "ANALYSIS_SUMMARY_COLUMNS",
    "AnalysisResult",
    "load_analysis_outputs",
    "run_dynamic_analysis",
    "write_analysis_outputs",
]
