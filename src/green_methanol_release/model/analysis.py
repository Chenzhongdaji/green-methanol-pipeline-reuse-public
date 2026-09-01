"""Dynamic account analysis and model-derived Figure 4/5 source tables."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

import pandas as pd

from .config import YEARS, SCENARIOS, TIERS, load_config
from .demand import DemandResult, DEMAND_INPUTS, preprocess_demand
from .io import hashes_for_paths, sorted_frame, write_csv, write_json
from .network import NETWORK_INPUTS, NetworkResult, _read_candidate_links, run_network


ANALYSIS_INPUTS = {
    **DEMAND_INPUTS,
    **NETWORK_INPUTS,
}

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
    relaxed = run_network(
        root,
        demand,
        capacity_factor=config_factor,
        scenarios=scenarios,
    )
    candidate_map, selected = _read_candidate_links(root)
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
                    "source_type": "public_directed_model_counterfactual",
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
    regional = _regional_accounts(network_result)
    figure_04 = _figure_04_source(regional)
    figure_05 = _figure_05_source(root, demand_result, network_result, config.capacity_relaxation_factor)
    summary = _analysis_summary(network_result)
    if (regional["demand_methanol_10kt"] - regional["served_methanol_10kt"] - regional["unserved_methanol_10kt"]).abs().max() > 1e-8:
        raise RuntimeError("regional demand accounts do not close")
    input_hashes = hashes_for_paths(root, ANALYSIS_INPUTS.values())
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
        },
        "boundary": "regional and logistics metrics are model-derived accounts; they are not observations or segment qualification decisions",
    }
    return AnalysisResult(summary, regional, figure_04, figure_05, audit, input_hashes)


def write_analysis_outputs(result: AnalysisResult, root: Path) -> list[str]:
    """Persist analysis tables and the model-derived Figure 4/5 source carriers."""

    output_dir = Path(root).resolve() / "data" / "processed" / "model_v01"
    write_csv(result.summary, output_dir / "analysis_summary.csv")
    write_csv(result.regional_accounts, output_dir / "regional_accounts.csv")
    write_csv(result.figure_04_source, output_dir / "figure_04_source.csv")
    write_csv(result.figure_05_source, output_dir / "figure_05_source.csv")
    write_json(result.audit, output_dir / "dynamic_analysis_audit.json")
    return [
        "data/processed/model_v01/analysis_summary.csv",
        "data/processed/model_v01/regional_accounts.csv",
        "data/processed/model_v01/figure_04_source.csv",
        "data/processed/model_v01/figure_05_source.csv",
        "data/processed/model_v01/dynamic_analysis_audit.json",
    ]


__all__ = ["AnalysisResult", "run_dynamic_analysis", "write_analysis_outputs"]
