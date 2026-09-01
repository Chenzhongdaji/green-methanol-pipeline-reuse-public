"""Directed pipeline capacity and min-cost flow model for public carriers."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any, Iterable

import networkx as nx
import pandas as pd

from .config import YEARS, ModelConfig, load_config
from .demand import DemandResult, DEMAND_INPUTS, preprocess_demand
from .io import finite_float, hashes_for_paths, normalize_province, read_csv, sorted_frame, write_csv, write_json


NETWORK_INPUTS = {
    "pipeline_segments": "data/raw/pipeline/pipeline_network_segments_v01.csv",
    "pipeline_nodes": "data/raw/pipeline/pipeline_nodes_geocoded.csv",
    "segment_tasks": "data/raw/pipeline/segment_transport_task_pipeline_adjusted_long.csv",
    "candidate_links": "data/raw/topology/candidate_links.csv",
    "selected_plans": "data/raw/topology/best_two_link_plans.csv",
    "parameters": "config/model_parameters_v01.csv",
}


@dataclass(frozen=True)
class NetworkResult:
    summary: pd.DataFrame
    edge_flows: pd.DataFrame
    service: pd.DataFrame
    audit: dict[str, Any]
    input_hashes: dict[str, str]


def _read_segments(root: Path) -> pd.DataFrame:
    frame = read_csv(root, NETWORK_INPUTS["pipeline_segments"])
    expected = (
        "segment_id",
        "pipeline_name",
        "from_node_name",
        "to_node_name",
        "from_node_id",
        "to_node_id",
        "from_lon",
        "from_lat",
        "to_lon",
        "to_lat",
        "design_throughput_10kt_y",
        "commissioning_year",
        "direction_description",
        "coordinate_note",
    )
    if tuple(frame.columns) != expected:
        raise ValueError("pipeline segment carrier schema is not the public English schema")
    for field in ("from_lon", "from_lat", "to_lon", "to_lat", "design_throughput_10kt_y", "commissioning_year"):
        frame[field] = pd.to_numeric(frame[field], errors="raise")
    if frame["segment_id"].duplicated().any():
        raise ValueError("pipeline segment IDs must be unique")
    if (frame["design_throughput_10kt_y"] < 0).any():
        raise ValueError("pipeline design throughput must be non-negative")
    return frame.sort_values("segment_id", kind="mergesort").reset_index(drop=True)


def _read_node_provinces(root: Path) -> dict[str, str]:
    frame = read_csv(root, NETWORK_INPUTS["pipeline_nodes"])
    if frame.shape[1] < 5:
        raise ValueError("pipeline node carrier has fewer than five columns")
    node_ids = frame.iloc[:, 0].astype(str).str.strip()
    provinces = frame.iloc[:, 4].map(normalize_province)
    if node_ids.eq("").any() or provinces.eq("").any():
        raise ValueError("pipeline node carrier has blank node or province")
    if node_ids.duplicated().any():
        raise ValueError("pipeline node IDs must be unique")
    return {node: province for node, province in zip(node_ids, provinces, strict=True)}


def _read_segment_tasks(root: Path, segments: pd.DataFrame) -> pd.DataFrame:
    frame = read_csv(root, NETWORK_INPUTS["segment_tasks"])
    if frame.shape[1] < 11:
        raise ValueError("segment task carrier has fewer than eleven columns")
    tasks = pd.DataFrame(
        {
            "segment_id": frame.iloc[:, 0].astype(str).str.strip(),
            "year": pd.to_numeric(frame.iloc[:, 4], errors="raise").astype(int),
            "network_task_10kt": pd.to_numeric(frame.iloc[:, 10], errors="raise"),
        }
    )
    if tasks.duplicated(["segment_id", "year"]).any():
        raise ValueError("segment task carrier repeats segment/year")
    expected = {(str(segment), year) for segment in segments["segment_id"] for year in YEARS}
    actual = set(zip(tasks["segment_id"], tasks["year"], strict=True))
    if actual != expected:
        missing = sorted(expected - actual)[:5]
        extra = sorted(actual - expected)[:5]
        raise ValueError(f"segment task carrier does not cover every segment/year: missing={missing}, extra={extra}")
    if tasks["network_task_10kt"].isna().any() or (tasks["network_task_10kt"] < 0).any():
        raise ValueError("segment task carrier has invalid network task values")
    return tasks.sort_values(["segment_id", "year"], kind="mergesort").reset_index(drop=True)


def _read_candidate_links(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    candidates = read_csv(root, NETWORK_INPUTS["candidate_links"])
    required = {
        "candidate_id",
        "from_node_id",
        "to_node_id",
        "distance_km",
        "capacity_10kt",
    }
    if not required.issubset(candidates.columns):
        raise ValueError("candidate-link carrier is missing required columns")
    candidates = candidates.copy()
    candidates["distance_km"] = pd.to_numeric(candidates["distance_km"], errors="raise")
    candidates["capacity_10kt"] = pd.to_numeric(candidates["capacity_10kt"], errors="raise")
    if candidates["candidate_id"].duplicated().any() or (candidates[["distance_km", "capacity_10kt"]] < 0).any().any():
        raise ValueError("candidate-link carrier has duplicate IDs or negative values")
    mapping = {
        str(row.candidate_id): {
            "candidate_id": str(row.candidate_id),
            "from_node_id": str(row.from_node_id),
            "to_node_id": str(row.to_node_id),
            "distance_km": float(row.distance_km),
            "capacity_10kt": float(row.capacity_10kt),
        }
        for row in candidates.sort_values("candidate_id", kind="mergesort").itertuples(index=False)
    }
    plans = read_csv(root, NETWORK_INPUTS["selected_plans"])
    if not {"scenario", "first_candidate_id"}.issubset(plans.columns):
        raise ValueError("selected-plan carrier is missing scenario/candidate columns")
    selected: dict[str, str] = {}
    for row in plans.sort_values(["scenario", "first_candidate_id"], kind="mergesort").itertuples(index=False):
        scenario = str(row.scenario)
        candidate = str(row.first_candidate_id)
        if scenario in selected:
            continue
        if candidate != "" and candidate != "nan":
            if candidate not in mapping:
                raise ValueError(f"selected plan references unknown candidate {candidate}")
            selected[scenario] = candidate
    return mapping, selected


def _units(value: float, scale: int) -> int:
    if value <= 0:
        return 0
    # Flooring preserves the physical upper bound after fixed-point scaling:
    # a rounded residual can otherwise exceed a province's unserved demand by
    # a fraction of one model unit and break the served-account closure.
    return max(0, int(math.floor(value * scale + 1e-9)))


def _from_units(value: int, scale: int) -> float:
    return float(value) / float(scale)


def _graph_for_case(
    segments: pd.DataFrame,
    tasks: pd.DataFrame,
    node_provinces: dict[str, str],
    supply: dict[str, float],
    demand: dict[str, float],
    config: ModelConfig,
    *,
    year: int,
    capacity_factor: float,
    candidate_links: Iterable[dict[str, Any]] = (),
) -> tuple[nx.DiGraph, dict[str, str], dict[str, str], dict[str, dict[str, Any]]]:
    graph = nx.DiGraph()
    source = "__source__"
    sink = "__sink__"
    graph.add_nodes_from((source, sink))
    supply_aggregates: dict[str, str] = {}
    demand_aggregates: dict[str, str] = {}
    segment_edges: dict[str, dict[str, Any]] = {}
    task_lookup = tasks[tasks["year"].eq(year)].set_index("segment_id")
    active = segments[segments["commissioning_year"].le(year)].copy()
    for row in active.sort_values("segment_id", kind="mergesort").itertuples(index=False):
        segment_id = str(row.segment_id)
        from_node = str(row.from_node_id)
        to_node = str(row.to_node_id)
        baseline_task = float(task_lookup.loc[segment_id, "network_task_10kt"])
        spare = max(0.0, float(row.design_throughput_10kt_y) - baseline_task) * capacity_factor
        capacity = _units(spare, config.flow_scale)
        if capacity <= 0:
            continue
        pipe_from = f"PIPE::{from_node}"
        pipe_to = f"PIPE::{to_node}"
        segment_node = f"SEG::{segment_id}"
        distance = math.hypot(float(row.to_lon) - float(row.from_lon), float(row.to_lat) - float(row.from_lat))
        # Use an analytical coordinate distance converted to a positive integer
        # routing cost. It is a ranking cost, not a geographic distance claim.
        weight = max(1, int(round(distance * 1000.0 * config.transport_cost_per_km)))
        graph.add_edge(pipe_from, segment_node, capacity=capacity, weight=0)
        graph.add_edge(segment_node, pipe_to, capacity=capacity, weight=weight)
        segment_edges[segment_id] = {
            "segment_node": segment_node,
            "to_node": pipe_to,
            "capacity_units": capacity,
            "capacity_10kt": spare,
            "distance_km": distance,
            "weight": weight,
            "from_node_id": from_node,
            "to_node_id": to_node,
        }

    for candidate in sorted(candidate_links, key=lambda item: str(item["candidate_id"])):
        from_node = str(candidate["from_node_id"])
        to_node = str(candidate["to_node_id"])
        capacity = _units(float(candidate["capacity_10kt"]) * capacity_factor, config.flow_scale)
        if capacity <= 0 or from_node not in node_provinces or to_node not in node_provinces:
            continue
        pipe_from = f"PIPE::{from_node}"
        pipe_to = f"PIPE::{to_node}"
        candidate_node = f"CAND::{candidate['candidate_id']}"
        weight = max(1, int(round(float(candidate["distance_km"]) * 1000.0 * config.transport_cost_per_km)))
        graph.add_edge(pipe_from, candidate_node, capacity=capacity, weight=0)
        graph.add_edge(candidate_node, pipe_to, capacity=capacity, weight=weight)

    nodes_by_province: dict[str, list[str]] = {}
    for node_id, province in sorted(node_provinces.items()):
        nodes_by_province.setdefault(province, []).append(node_id)

    for province in sorted(supply):
        amount = _units(supply[province], config.flow_scale)
        pipeline_nodes = nodes_by_province.get(province, [])
        if amount <= 0 or not pipeline_nodes:
            continue
        aggregate = f"SUPPLY::{province}"
        supply_aggregates[province] = aggregate
        graph.add_edge(source, aggregate, capacity=amount, weight=0)
        for node_id in pipeline_nodes:
            graph.add_edge(aggregate, f"PIPE::{node_id}", capacity=amount, weight=0)

    for province in sorted(demand):
        amount = _units(demand[province], config.flow_scale)
        pipeline_nodes = nodes_by_province.get(province, [])
        if amount <= 0 or not pipeline_nodes:
            continue
        aggregate = f"DEMAND::{province}"
        demand_aggregates[province] = aggregate
        for node_id in pipeline_nodes:
            graph.add_edge(f"PIPE::{node_id}", aggregate, capacity=amount, weight=0)
        graph.add_edge(aggregate, sink, capacity=amount, weight=0)
    return graph, supply_aggregates, demand_aggregates, segment_edges


def _solve_graph(graph: nx.DiGraph, config: ModelConfig) -> tuple[int, int, dict[str, dict[str, int]]]:
    if not graph.has_node("__source__") or not graph.has_node("__sink__"):
        return 0, 0, {}
    maximum = int(nx.maximum_flow_value(graph, "__source__", "__sink__", capacity="capacity"))
    if maximum <= 0:
        return 0, 0, {}
    flow = nx.max_flow_min_cost(graph, "__source__", "__sink__", capacity="capacity", weight="weight")
    objective = 0
    for upstream, downstream, values in graph.edges(data=True):
        objective += int(flow.get(upstream, {}).get(downstream, 0)) * int(values.get("weight", 0))
    return maximum, int(objective), flow


def _case_inputs(
    demand: DemandResult,
    scenario: str,
    tier: str,
    year: int,
) -> tuple[dict[str, float], dict[str, float], float]:
    demand_frame = demand.nodes[
        demand.nodes["scenario"].eq(scenario)
        & demand.nodes["tier"].eq(tier)
        & demand.nodes["year"].eq(year)
    ]
    demand_by_province = {
        str(key): float(value)
        for key, value in demand_frame.groupby("province_key", sort=True)["demand_10kt"].sum().items()
    }
    supply_frame = demand.supply[demand.supply["tier"].eq(tier) & demand.supply["year"].eq(year)]
    supply_by_province = {
        str(key): float(value)
        for key, value in supply_frame.groupby("province_key", sort=True)["supply_10kt"].sum().items()
    }
    local = math.fsum(min(supply_by_province.get(province, 0.0), amount) for province, amount in demand_by_province.items())
    residual_demand = {
        province: max(0.0, amount - min(amount, supply_by_province.get(province, 0.0)))
        for province, amount in demand_by_province.items()
    }
    residual_supply = {
        province: max(0.0, amount - min(amount, demand_by_province.get(province, 0.0)))
        for province, amount in supply_by_province.items()
    }
    return residual_supply, residual_demand, local


def run_network(
    root: Path,
    demand: DemandResult | None = None,
    *,
    capacity_factor: float = 1.0,
    connector_by_scenario: dict[str, list[dict[str, Any]]] | None = None,
    scenarios: Iterable[str] | None = None,
) -> NetworkResult:
    """Solve all requested scenario/tier/year cases on the public directed graph."""

    root = Path(root).resolve()
    config = load_config(root)
    demand_result = preprocess_demand(root) if demand is None else demand
    segments = _read_segments(root)
    node_provinces = _read_node_provinces(root)
    tasks = _read_segment_tasks(root, segments)
    requested = tuple(scenarios) if scenarios is not None else tuple(sorted(demand_result.nodes["scenario"].unique()))
    rows: list[dict[str, Any]] = []
    edge_rows: list[dict[str, Any]] = []
    service_rows: list[dict[str, Any]] = []
    connector_by_scenario = connector_by_scenario or {}
    for scenario in requested:
        for tier in sorted(demand_result.nodes["tier"].unique(), key=("low", "mid", "high").index):
            for year in YEARS:
                residual_supply, residual_demand, local = _case_inputs(demand_result, scenario, tier, year)
                graph, supply_aggs, demand_aggs, segment_edges = _graph_for_case(
                    segments,
                    tasks,
                    node_provinces,
                    residual_supply,
                    residual_demand,
                    config,
                    year=year,
                    capacity_factor=capacity_factor,
                    candidate_links=connector_by_scenario.get(scenario, []),
                )
                maximum, objective, flow = _solve_graph(graph, config)
                pipeline_served = _from_units(maximum, config.flow_scale)
                supply_used = {
                    province: _from_units(int(flow.get("__source__", {}).get(aggregate, 0)), config.flow_scale)
                    for province, aggregate in supply_aggs.items()
                }
                served_by_province = {
                    province: _from_units(int(flow.get(aggregate, {}).get("__sink__", 0)), config.flow_scale)
                    for province, aggregate in demand_aggs.items()
                }
                demand_frame = demand_result.nodes[
                    demand_result.nodes["scenario"].eq(scenario)
                    & demand_result.nodes["tier"].eq(tier)
                    & demand_result.nodes["year"].eq(year)
                ]
                demand_by_province = {
                    str(key): float(value)
                    for key, value in demand_frame.groupby("province_key", sort=True)["demand_10kt"].sum().items()
                }
                supply_frame = demand_result.supply[
                    demand_result.supply["tier"].eq(tier) & demand_result.supply["year"].eq(year)
                ]
                supply_by_province = {
                    str(key): float(value)
                    for key, value in supply_frame.groupby("province_key", sort=True)["supply_10kt"].sum().items()
                }
                flow_tonne_km = 0.0
                used_edges = 0
                max_util = 0.0
                for segment_id in sorted(segment_edges):
                    metadata = segment_edges[segment_id]
                    flow_units = int(flow.get(metadata["segment_node"], {}).get(metadata["to_node"], 0))
                    amount = _from_units(flow_units, config.flow_scale)
                    if amount <= 0:
                        continue
                    capacity = float(metadata["capacity_10kt"])
                    utilization = 100.0 * amount / capacity if capacity else 0.0
                    flow_tonne_km += amount * metadata["distance_km"] * 10000.0
                    used_edges += 1
                    max_util = max(max_util, utilization)
                    edge_rows.append(
                        {
                            "scenario": scenario,
                            "tier": tier,
                            "year": year,
                            "segment_id": segment_id,
                            "from_node_id": metadata["from_node_id"],
                            "to_node_id": metadata["to_node_id"],
                            "flow_10kt": amount,
                            "capacity_10kt": capacity,
                            "flow_to_capacity_pct": utilization,
                            "distance_km": metadata["distance_km"],
                        }
                    )
                for province in sorted(demand_by_province):
                    demand_amount = demand_by_province[province]
                    local_amount = min(demand_amount, supply_by_province.get(province, 0.0))
                    pipeline_amount = served_by_province.get(province, 0.0)
                    served_amount = min(demand_amount, local_amount + pipeline_amount)
                    service_rows.append(
                        {
                            "scenario": scenario,
                            "tier": tier,
                            "year": year,
                            "province_key": province,
                            "demand_10kt": demand_amount,
                            "supply_10kt": supply_by_province.get(province, 0.0),
                            "local_direct_10kt": local_amount,
                            "pipeline_served_10kt": pipeline_amount,
                            "served_10kt": served_amount,
                            "unserved_10kt": max(0.0, demand_amount - served_amount),
                        }
                    )
                total_demand = math.fsum(demand_by_province.values())
                total_served = min(total_demand, local + pipeline_served)
                total_supply = math.fsum(supply_by_province.values())
                rows.append(
                    {
                        "scenario": scenario,
                        "tier": tier,
                        "year": year,
                        "demand_10kt": total_demand,
                        "supply_10kt": total_supply,
                        "local_direct_10kt": local,
                        "pipeline_served_10kt": pipeline_served,
                        "served_10kt": total_served,
                        "unserved_10kt": max(0.0, total_demand - total_served),
                        "demand_met_pct": 100.0 * total_served / total_demand if total_demand else 0.0,
                        "pipeline_tonne_km": flow_tonne_km,
                        "edges_used": used_edges,
                        "max_edge_util_pct": max_util,
                        "min_cost_objective": objective,
                        "active_segments": len(segment_edges),
                        "capacity_factor": capacity_factor,
                        "connector_count": len(connector_by_scenario.get(scenario, [])),
                    }
                )
    summary = sorted_frame(pd.DataFrame(rows), ("scenario", "tier", "year"))
    edge_flows = sorted_frame(
        pd.DataFrame(
            edge_rows,
            columns=[
                "scenario",
                "tier",
                "year",
                "segment_id",
                "from_node_id",
                "to_node_id",
                "flow_10kt",
                "capacity_10kt",
                "flow_to_capacity_pct",
                "distance_km",
            ],
        ),
        ("scenario", "tier", "year", "segment_id"),
    )
    service = sorted_frame(pd.DataFrame(service_rows), ("scenario", "tier", "year", "province_key"))
    if summary.empty or service.empty:
        raise RuntimeError("directed network model returned no cases")
    served_error = summary["served_10kt"] - summary["local_direct_10kt"] - summary["pipeline_served_10kt"]
    if served_error.abs().max() > 1e-8:
        offender = summary.loc[served_error.abs().idxmax()]
        raise RuntimeError(
            "network served account does not close: "
            f"{offender['scenario']}/{offender['tier']}/{offender['year']} "
            f"served={offender['served_10kt']} local={offender['local_direct_10kt']} "
            f"pipeline={offender['pipeline_served_10kt']}"
        )
    if (summary["demand_10kt"] - summary["served_10kt"] - summary["unserved_10kt"]).abs().max() > 1e-8:
        raise RuntimeError("network demand account does not close")
    input_paths = {**NETWORK_INPUTS, **{key: value for key, value in DEMAND_INPUTS.items() if key not in {"candidate_links", "selected_plans"}}}
    input_hashes = hashes_for_paths(root, input_paths.values())
    audit = {
        "status": "PASS",
        "stage": "directed_network_flow",
        "solver": "NetworkX maximum-flow followed by max-flow-min-cost",
        "network_variant": "base" if capacity_factor == 1.0 and not connector_by_scenario else "counterfactual_capacity_or_connector",
        "capacity_factor": capacity_factor,
        "input_paths": sorted(input_paths.values()),
        "input_hashes": input_hashes,
        "schema": {
            "summary": list(summary.columns),
            "edge_flows": list(edge_flows.columns),
            "service": list(service.columns),
        },
        "rows": {
            "summary": int(len(summary)),
            "edge_flows": int(len(edge_flows)),
            "service": int(len(service)),
        },
        "boundary": "capacity-constrained directed model on author-derived segment and node carriers; no engineering qualification is inferred",
    }
    return NetworkResult(summary, edge_flows, service, audit, input_hashes)


def write_network_outputs(result: NetworkResult, root: Path) -> list[str]:
    """Persist the base directed-flow stage to release-relative paths."""

    output_dir = Path(root).resolve() / "data" / "processed" / "model_v01"
    write_csv(result.summary, output_dir / "network_summary.csv")
    write_csv(result.edge_flows, output_dir / "network_edge_flows.csv")
    write_csv(result.service, output_dir / "network_service.csv")
    write_json(result.audit, output_dir / "network_model_audit.json")
    return [
        "data/processed/model_v01/network_summary.csv",
        "data/processed/model_v01/network_edge_flows.csv",
        "data/processed/model_v01/network_service.csv",
        "data/processed/model_v01/network_model_audit.json",
    ]


__all__ = ["NETWORK_INPUTS", "NetworkResult", "run_network", "write_network_outputs"]
