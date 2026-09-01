"""Directed pipeline capacity and min-cost flow model for public carriers."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any, Iterable

import networkx as nx
import pandas as pd

from .config import YEARS, ModelConfig, load_config
from .demand import DEMAND_OUTPUTS, DemandResult, preprocess_demand
from .io import (
    finite_float,
    hashes_for_paths,
    normalize_province,
    read_csv,
    read_json,
    sorted_frame,
    write_csv,
    write_json,
)


NETWORK_INPUTS = {
    "pipeline_segments": "data/raw/pipeline/pipeline_network_segments_v01.csv",
    "pipeline_nodes": "data/raw/pipeline/pipeline_nodes_geocoded.csv",
    "segment_tasks": "data/raw/pipeline/segment_transport_task_pipeline_adjusted_long.csv",
    "parameters": "config/model_parameters_v01.csv",
}
NETWORK_STAGE_INPUTS = {
    **{
        "demand_nodes": DEMAND_OUTPUTS["nodes"],
        "demand_totals": DEMAND_OUTPUTS["totals"],
        "demand_supply": DEMAND_OUTPUTS["supply"],
        "demand_components": DEMAND_OUTPUTS["components"],
        "demand_audit": DEMAND_OUTPUTS["audit"],
    },
    **NETWORK_INPUTS,
}
CANDIDATE_INPUTS = {
    "candidate_links": "data/raw/topology/candidate_links.csv",
    "selected_plans": "data/raw/topology/best_two_link_plans.csv",
}
NETWORK_OUTPUTS = {
    "summary": "data/processed/model_v01/network_summary.csv",
    "edge_flows": "data/processed/model_v01/network_edge_flows.csv",
    "service": "data/processed/model_v01/network_service.csv",
    "edge_catalog": "data/processed/model_v01/network_edge_catalog.csv",
    "node_catalog": "data/processed/model_v01/network_node_catalog.csv",
    "audit": "data/processed/model_v01/network_model_audit.json",
}

NETWORK_NODE_COLUMNS = (
    "node_id",
    "province_key",
    "longitude",
    "latitude",
)
NETWORK_EDGE_CATALOG_COLUMNS = (
    "year",
    "segment_id",
    "from_node_id",
    "to_node_id",
    "from_province",
    "to_province",
    "design_throughput_10kt_y",
    "same_pipeline_task_10kt",
    "capacity_10kt",
    "distance_km",
    "capacity_basis",
)
NETWORK_SUMMARY_COLUMNS = (
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
    "pipeline_tonne_km",
    "edges_used",
    "max_edge_util_pct",
    "min_cost_objective",
    "active_segments",
    "capacity_factor",
    "connector_count",
)
NETWORK_EDGE_FLOW_COLUMNS = (
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
    "capacity_basis",
)
NETWORK_SERVICE_COLUMNS = (
    "scenario",
    "tier",
    "year",
    "province_key",
    "demand_10kt",
    "supply_10kt",
    "local_direct_10kt",
    "pipeline_served_10kt",
    "served_10kt",
    "unserved_10kt",
)
SEGMENT_TASK_CAPACITY_COLUMN = "同管道运输任务_万吨"


@dataclass(frozen=True)
class NetworkTopology:
    """Persistable base topology used by analysis-stage counterfactuals."""

    nodes: pd.DataFrame
    edges: pd.DataFrame
    input_hashes: dict[str, str]


@dataclass(frozen=True)
class NetworkResult:
    summary: pd.DataFrame
    edge_flows: pd.DataFrame
    service: pd.DataFrame
    audit: dict[str, Any]
    input_hashes: dict[str, str]
    edge_catalog: pd.DataFrame | None = None
    node_catalog: pd.DataFrame | None = None
    topology: NetworkTopology | None = None


def haversine_km(lon1: object, lat1: object, lon2: object, lat2: object) -> float:
    """Return WGS84 great-circle distance in kilometres."""

    first_lon = finite_float(lon1, "longitude")
    first_lat = finite_float(lat1, "latitude")
    second_lon = finite_float(lon2, "longitude")
    second_lat = finite_float(lat2, "latitude")
    if not all(-180.0 <= value <= 180.0 for value in (first_lon, second_lon)):
        raise ValueError("longitude must lie in [-180, 180]")
    if not all(-90.0 <= value <= 90.0 for value in (first_lat, second_lat)):
        raise ValueError("latitude must lie in [-90, 90]")
    radius_km = 6371.0088
    first_lat_rad = math.radians(first_lat)
    second_lat_rad = math.radians(second_lat)
    delta_lat = math.radians(second_lat - first_lat)
    delta_lon = math.radians(second_lon - first_lon)
    hav = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(first_lat_rad)
        * math.cos(second_lat_rad)
        * math.sin(delta_lon / 2.0) ** 2
    )
    return 2.0 * radius_km * math.atan2(math.sqrt(hav), math.sqrt(max(0.0, 1.0 - hav)))


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
    for field in (
        "from_lon",
        "from_lat",
        "to_lon",
        "to_lat",
        "design_throughput_10kt_y",
        "commissioning_year",
    ):
        frame[field] = pd.to_numeric(frame[field], errors="raise")
    if frame["segment_id"].duplicated().any():
        raise ValueError("pipeline segment IDs must be unique")
    if (frame["design_throughput_10kt_y"] < 0).any():
        raise ValueError("pipeline design throughput must be non-negative")
    # The original v08 routing helper applied a one-kilometre lower bound to
    # coincident analytical coordinates; retain that convention for base
    # segments as well as candidate links while keeping Haversine kilometres
    # for all non-coincident geometry.
    frame["distance_km"] = frame.apply(
        lambda row: max(
            haversine_km(
                row["from_lon"], row["from_lat"], row["to_lon"], row["to_lat"]
            ),
            1.0,
        ),
        axis=1,
    )
    return frame.sort_values("segment_id", kind="mergesort").reset_index(drop=True)


def _read_node_catalog(root: Path) -> pd.DataFrame:
    frame = read_csv(root, NETWORK_INPUTS["pipeline_nodes"])
    if frame.shape[1] < 7:
        raise ValueError("pipeline node carrier has fewer than seven columns")
    catalog = pd.DataFrame(
        {
            "node_id": frame.iloc[:, 0].astype(str).str.strip(),
            "province_key": frame.iloc[:, 4].map(normalize_province),
            "longitude": pd.to_numeric(frame.iloc[:, 5], errors="raise"),
            "latitude": pd.to_numeric(frame.iloc[:, 6], errors="raise"),
        }
    )
    if catalog["node_id"].eq("").any() or catalog["province_key"].eq("").any():
        raise ValueError("pipeline node carrier has blank node or province")
    if catalog["node_id"].duplicated().any():
        raise ValueError("pipeline node IDs must be unique")
    for row in catalog.itertuples(index=False):
        haversine_km(row.longitude, row.latitude, row.longitude, row.latitude)
    return sorted_frame(catalog, ("node_id",))


def _read_node_provinces(root: Path) -> dict[str, str]:
    catalog = _read_node_catalog(root)
    return dict(zip(catalog["node_id"], catalog["province_key"], strict=True))


def _read_segment_tasks(root: Path, segments: pd.DataFrame) -> pd.DataFrame:
    frame = read_csv(root, NETWORK_INPUTS["segment_tasks"])
    if frame.shape[1] < 11 or frame.columns[6] != SEGMENT_TASK_CAPACITY_COLUMN:
        raise ValueError(
            "segment task carrier must expose 同管道运输任务_万吨 at the public schema position"
        )
    tasks = pd.DataFrame(
        {
            "segment_id": frame.iloc[:, 0].astype(str).str.strip(),
            "year": pd.to_numeric(frame.iloc[:, 4], errors="raise").astype(int),
            "same_pipeline_task_10kt": pd.to_numeric(frame.iloc[:, 6], errors="raise"),
        }
    )
    if tasks.duplicated(["segment_id", "year"]).any():
        raise ValueError("segment task carrier repeats segment/year")
    expected = {(str(segment), year) for segment in segments["segment_id"] for year in YEARS}
    actual = set(zip(tasks["segment_id"], tasks["year"], strict=True))
    if actual != expected:
        missing = sorted(expected - actual)[:5]
        extra = sorted(actual - expected)[:5]
        raise ValueError(
            f"segment task carrier does not cover every segment/year: missing={missing}, extra={extra}"
        )
    if (
        tasks["same_pipeline_task_10kt"].isna().any()
        or ~tasks["same_pipeline_task_10kt"].map(math.isfinite).all()
        or (tasks["same_pipeline_task_10kt"] < 0).any()
    ):
        raise ValueError("segment task carrier has invalid same-pipeline task values")
    return tasks.sort_values(["segment_id", "year"], kind="mergesort").reset_index(drop=True)


def _read_candidate_links(
    root: Path,
    node_provinces: dict[str, str] | None = None,
    node_coordinates: dict[str, tuple[float, float]] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Read Figure-5 candidates and validate endpoints against the base nodes."""

    candidates = read_csv(root, CANDIDATE_INPUTS["candidate_links"])
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
    candidates["candidate_id"] = candidates["candidate_id"].astype(str).str.strip()
    candidates["from_node_id"] = candidates["from_node_id"].astype(str).str.strip()
    candidates["to_node_id"] = candidates["to_node_id"].astype(str).str.strip()
    candidates["distance_km"] = pd.to_numeric(candidates["distance_km"], errors="raise")
    candidates["capacity_10kt"] = pd.to_numeric(candidates["capacity_10kt"], errors="raise")
    if candidates["candidate_id"].duplicated().any() or (
        candidates[["distance_km", "capacity_10kt"]] < 0
    ).any().any():
        raise ValueError("candidate-link carrier has duplicate IDs or negative values")
    if node_provinces is not None:
        known_nodes = set(node_provinces)
        unknown = sorted(
            (set(candidates["from_node_id"]) | set(candidates["to_node_id"])) - known_nodes
        )
        if unknown:
            raise ValueError(f"candidate link references unknown public node(s): {unknown[:5]}")
    if node_coordinates is not None:
        for row in candidates.itertuples(index=False):
            try:
                from_coord = node_coordinates[str(row.from_node_id)]
                to_coord = node_coordinates[str(row.to_node_id)]
            except KeyError as exc:
                raise ValueError(
                    f"candidate link references unknown public node: {exc.args[0]}"
                ) from exc
            # A one-kilometre floor preserves the original v08 routing-cost
            # convention for coincident analytical node coordinates while
            # keeping all non-coincident candidates on the haversine km scale.
            derived = max(haversine_km(*from_coord, *to_coord), 1.0)
            if abs(float(row.distance_km) - derived) > 0.01:
                raise ValueError(
                    f"candidate {row.candidate_id} distance_km is not the haversine distance"
                )

    mapping: dict[str, dict[str, Any]] = {}
    for row in candidates.sort_values("candidate_id", kind="mergesort").itertuples(index=False):
        distance = float(row.distance_km)
        if node_coordinates is not None:
            distance = max(haversine_km(
                *node_coordinates[str(row.from_node_id)],
                *node_coordinates[str(row.to_node_id)],
            ), 1.0)
        mapping[str(row.candidate_id)] = {
            "candidate_id": str(row.candidate_id),
            "from_node_id": str(row.from_node_id),
            "to_node_id": str(row.to_node_id),
            "distance_km": distance,
            "capacity_10kt": float(row.capacity_10kt),
        }
    plans = read_csv(root, CANDIDATE_INPUTS["selected_plans"])
    if not {"scenario", "first_candidate_id"}.issubset(plans.columns):
        raise ValueError("selected-plan carrier is missing scenario/candidate columns")
    selected: dict[str, str] = {}
    for row in plans.sort_values(
        ["scenario", "first_candidate_id"], kind="mergesort"
    ).itertuples(index=False):
        scenario = str(row.scenario)
        candidate = str(row.first_candidate_id)
        if scenario in selected:
            continue
        if candidate and candidate != "nan":
            if candidate not in mapping:
                raise ValueError(f"selected plan references unknown candidate {candidate}")
            selected[scenario] = candidate
    return mapping, selected


def _build_edge_catalog(
    segments: pd.DataFrame,
    tasks: pd.DataFrame,
    node_catalog: pd.DataFrame,
) -> pd.DataFrame:
    node_provinces = dict(zip(node_catalog["node_id"], node_catalog["province_key"], strict=True))
    task_lookup = tasks.set_index(["segment_id", "year"])["same_pipeline_task_10kt"]
    rows: list[dict[str, Any]] = []
    for segment in segments.sort_values("segment_id", kind="mergesort").itertuples(index=False):
        from_node = str(segment.from_node_id)
        to_node = str(segment.to_node_id)
        if from_node not in node_provinces or to_node not in node_provinces:
            raise ValueError(f"segment {segment.segment_id} references unknown public node")
        for year in YEARS:
            if int(segment.commissioning_year) > year:
                continue
            same_task = float(task_lookup.loc[(str(segment.segment_id), year)])
            design = float(segment.design_throughput_10kt_y)
            rows.append(
                {
                    "year": year,
                    "segment_id": str(segment.segment_id),
                    "from_node_id": from_node,
                    "to_node_id": to_node,
                    "from_province": node_provinces[from_node],
                    "to_province": node_provinces[to_node],
                    "design_throughput_10kt_y": design,
                    "same_pipeline_task_10kt": same_task,
                    "capacity_10kt": max(0.0, design - same_task),
                    "distance_km": float(segment.distance_km),
                    "capacity_basis": SEGMENT_TASK_CAPACITY_COLUMN,
                }
            )
    return sorted_frame(
        pd.DataFrame(rows, columns=NETWORK_EDGE_CATALOG_COLUMNS), ("year", "segment_id")
    )


def _units(value: float, scale: int) -> int:
    if value <= 0:
        return 0
    return max(0, int(math.floor(value * scale + 1e-9)))


def _from_units(value: int, scale: int) -> float:
    return float(value) / float(scale)


def _graph_for_case(
    edge_catalog: pd.DataFrame,
    node_provinces: dict[str, str],
    supply: dict[str, float],
    demand: dict[str, float],
    config: ModelConfig,
    *,
    year: int,
    capacity_factor: float,
    candidate_links: Iterable[dict[str, Any]] = (),
) -> tuple[
    nx.DiGraph,
    dict[str, str],
    dict[str, str],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    graph = nx.DiGraph()
    source = "__source__"
    sink = "__sink__"
    graph.add_nodes_from((source, sink))
    supply_aggregates: dict[str, str] = {}
    demand_aggregates: dict[str, str] = {}
    segment_edges: dict[str, dict[str, Any]] = {}
    connector_edges: dict[str, dict[str, Any]] = {}
    active = edge_catalog[edge_catalog["year"].eq(year)]
    for row in active.sort_values("segment_id", kind="mergesort").itertuples(index=False):
        segment_id = str(row.segment_id)
        from_node = str(row.from_node_id)
        to_node = str(row.to_node_id)
        base_capacity = float(row.capacity_10kt)
        capacity_10kt = base_capacity * capacity_factor
        capacity = _units(capacity_10kt, config.flow_scale)
        if capacity <= 0:
            continue
        pipe_from = f"PIPE::{from_node}"
        pipe_to = f"PIPE::{to_node}"
        segment_node = f"SEG::{segment_id}"
        distance = float(row.distance_km)
        weight = max(1, int(round(distance * 1000.0 * config.transport_cost_per_km)))
        graph.add_edge(pipe_from, segment_node, capacity=capacity, weight=0)
        graph.add_edge(segment_node, pipe_to, capacity=capacity, weight=weight)
        segment_edges[segment_id] = {
            "segment_node": segment_node,
            "to_node": pipe_to,
            "capacity_units": capacity,
            "capacity_10kt": capacity_10kt,
            "distance_km": distance,
            "weight": weight,
            "from_node_id": from_node,
            "to_node_id": to_node,
            "capacity_basis": str(row.capacity_basis),
        }

    for candidate in sorted(candidate_links, key=lambda item: str(item["candidate_id"])):
        from_node = str(candidate["from_node_id"])
        to_node = str(candidate["to_node_id"])
        if from_node not in node_provinces or to_node not in node_provinces:
            raise ValueError("candidate link references unknown public node")
        capacity_10kt = float(candidate["capacity_10kt"]) * capacity_factor
        capacity = _units(capacity_10kt, config.flow_scale)
        if capacity <= 0:
            continue
        pipe_from = f"PIPE::{from_node}"
        pipe_to = f"PIPE::{to_node}"
        candidate_id = str(candidate["candidate_id"])
        candidate_node = f"CAND::{candidate_id}"
        distance = float(candidate["distance_km"])
        weight = max(1, int(round(distance * 1000.0 * config.transport_cost_per_km)))
        graph.add_edge(pipe_from, candidate_node, capacity=capacity, weight=0)
        graph.add_edge(candidate_node, pipe_to, capacity=capacity, weight=weight)
        connector_edges[candidate_id] = {
            "segment_node": candidate_node,
            "to_node": pipe_to,
            "capacity_10kt": capacity_10kt,
            "distance_km": distance,
            "from_node_id": from_node,
            "to_node_id": to_node,
        }

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
    return graph, supply_aggregates, demand_aggregates, segment_edges, connector_edges


def _solve_graph(graph: nx.DiGraph) -> tuple[int, int, dict[str, dict[str, int]]]:
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


def validate_flow_conservation(
    graph: nx.DiGraph,
    flow: dict[str, dict[str, int]],
    *,
    source: str = "__source__",
    sink: str = "__sink__",
    tolerance: int = 0,
) -> dict[str, int]:
    """Validate node-wise conservation and source/sink accounting in flow units."""

    if source not in graph or sink not in graph:
        raise ValueError("flow conservation graph must include source and sink")

    def edge_value(upstream: str, downstream: str) -> int:
        return int(flow.get(upstream, {}).get(downstream, 0))

    max_internal_residual = 0
    for node in graph.nodes:
        incoming = sum(
            edge_value(upstream, node) for upstream in graph.predecessors(node)
        )
        outgoing = sum(
            edge_value(node, downstream) for downstream in graph.successors(node)
        )
        if node in {source, sink}:
            continue
        residual = abs(incoming - outgoing)
        max_internal_residual = max(max_internal_residual, residual)
        if residual > tolerance:
            raise ValueError(
                "flow conservation failed at node "
                f"{node!r}: inflow={incoming}, outflow={outgoing}"
            )

    source_inflow = sum(edge_value(upstream, source) for upstream in graph.predecessors(source))
    source_outflow = sum(edge_value(source, downstream) for downstream in graph.successors(source))
    sink_inflow = sum(edge_value(upstream, sink) for upstream in graph.predecessors(sink))
    sink_outflow = sum(edge_value(sink, downstream) for downstream in graph.successors(sink))
    if source_inflow or sink_outflow or abs(source_outflow - sink_inflow) > tolerance:
        raise ValueError(
            "flow conservation source/sink accounting failed: "
            f"source_in={source_inflow}, source_out={source_outflow}, "
            f"sink_in={sink_inflow}, sink_out={sink_outflow}"
        )
    return {
        "max_internal_residual_units": int(max_internal_residual),
        "max_source_sink_residual_units": int(abs(source_outflow - sink_inflow)),
    }


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
    local = math.fsum(
        min(supply_by_province.get(province, 0.0), amount)
        for province, amount in demand_by_province.items()
    )
    residual_demand = {
        province: max(0.0, amount - min(amount, supply_by_province.get(province, 0.0)))
        for province, amount in demand_by_province.items()
    }
    residual_supply = {
        province: max(0.0, amount - min(amount, demand_by_province.get(province, 0.0)))
        for province, amount in supply_by_province.items()
    }
    return residual_supply, residual_demand, local


def _raw_topology(root: Path) -> tuple[NetworkTopology, dict[str, str]]:
    segments = _read_segments(root)
    node_catalog = _read_node_catalog(root)
    tasks = _read_segment_tasks(root, segments)
    edge_catalog = _build_edge_catalog(segments, tasks, node_catalog)
    input_hashes = hashes_for_paths(root, NETWORK_INPUTS.values())
    topology = NetworkTopology(node_catalog, edge_catalog, input_hashes)
    return topology, input_hashes


def run_network(
    root: Path,
    demand: DemandResult | None = None,
    *,
    capacity_factor: float = 1.0,
    connector_by_scenario: dict[str, list[dict[str, Any]]] | None = None,
    scenarios: Iterable[str] | None = None,
    topology: NetworkTopology | None = None,
    config: ModelConfig | None = None,
) -> NetworkResult:
    """Solve requested cases on the public directed base topology."""

    root = Path(root).resolve()
    config = load_config(root) if config is None else config
    demand_result = preprocess_demand(root) if demand is None else demand
    if topology is None:
        topology, topology_hashes = _raw_topology(root)
    else:
        topology_hashes = topology.input_hashes
    node_catalog = topology.nodes
    edge_catalog = topology.edges
    node_provinces = dict(zip(node_catalog["node_id"], node_catalog["province_key"], strict=True))
    requested = tuple(scenarios) if scenarios is not None else tuple(
        sorted(demand_result.nodes["scenario"].unique(), key=lambda value: int(str(value)[1:]))
    )
    connector_by_scenario = connector_by_scenario or {}
    rows: list[dict[str, Any]] = []
    edge_rows: list[dict[str, Any]] = []
    service_rows: list[dict[str, Any]] = []
    flow_conservation_cases = 0
    max_internal_residual_units = 0
    max_source_sink_residual_units = 0
    for scenario in requested:
        for tier in sorted(demand_result.nodes["tier"].unique(), key=("low", "mid", "high").index):
            for year in YEARS:
                residual_supply, residual_demand, local = _case_inputs(demand_result, scenario, tier, year)
                graph, supply_aggs, demand_aggs, segment_edges, connector_edges = _graph_for_case(
                    edge_catalog,
                    node_provinces,
                    residual_supply,
                    residual_demand,
                    config,
                    year=year,
                    capacity_factor=capacity_factor,
                    candidate_links=connector_by_scenario.get(scenario, []),
                )
                maximum, objective, flow = _solve_graph(graph)
                conservation = validate_flow_conservation(graph, flow)
                flow_conservation_cases += 1
                max_internal_residual_units = max(
                    max_internal_residual_units,
                    conservation["max_internal_residual_units"],
                )
                max_source_sink_residual_units = max(
                    max_source_sink_residual_units,
                    conservation["max_source_sink_residual_units"],
                )
                pipeline_served = _from_units(maximum, config.flow_scale)
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
                            "capacity_basis": metadata["capacity_basis"],
                        }
                    )
                for candidate_id in sorted(connector_edges):
                    metadata = connector_edges[candidate_id]
                    flow_units = int(flow.get(metadata["segment_node"], {}).get(metadata["to_node"], 0))
                    amount = _from_units(flow_units, config.flow_scale)
                    flow_tonne_km += amount * metadata["distance_km"] * 10000.0
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
                        "active_segments": int(len(edge_catalog[edge_catalog["year"].eq(year)])),
                        "capacity_factor": capacity_factor,
                        "connector_count": len(connector_by_scenario.get(scenario, [])),
                    }
                )
    summary = sorted_frame(pd.DataFrame(rows, columns=NETWORK_SUMMARY_COLUMNS), ("scenario", "tier", "year"))
    edge_flows = sorted_frame(
        pd.DataFrame(edge_rows, columns=NETWORK_EDGE_FLOW_COLUMNS),
        ("scenario", "tier", "year", "segment_id"),
    )
    service = sorted_frame(
        pd.DataFrame(service_rows, columns=NETWORK_SERVICE_COLUMNS),
        ("scenario", "tier", "year", "province_key"),
    )
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
    demand_stage_files = tuple(DEMAND_OUTPUTS.values())
    if all((root / Path(*relative.split("/"))).is_file() for relative in demand_stage_files):
        demand_hashes = hashes_for_paths(root, demand_stage_files)
    else:
        # ``run_network`` also supports in-memory composition before the
        # demand writer runs.  The registered stage path is always hashed by
        # ``run_model_stage`` and by the write-through full chain.
        demand_hashes = demand_result.input_hashes
    input_hashes = {
        **{f"demand::{key}": value for key, value in demand_hashes.items()},
        **{f"network::{key}": value for key, value in topology_hashes.items()},
    }
    variant = "base" if capacity_factor == 1.0 and not connector_by_scenario else "candidate_sensitivity"
    audit = {
        "status": "PASS",
        "stage": "directed_network_flow",
        "solver": "NetworkX maximum-flow followed by max-flow-min-cost",
        "network_variant": variant,
        "candidate_scope": "Figure-5 sensitivity only; candidate links are excluded from the base graph",
        "capacity_factor": capacity_factor,
        "capacity_basis": SEGMENT_TASK_CAPACITY_COLUMN,
        "distance_method": "haversine WGS84 great-circle kilometres",
        "transport_emission": "reserved_not_implemented",
        "input_paths": sorted(set(DEMAND_OUTPUTS.values()) | set(NETWORK_INPUTS.values())),
        "input_hashes": input_hashes,
        "schema": {
            "summary": list(summary.columns),
            "edge_flows": list(edge_flows.columns),
            "service": list(service.columns),
            "edge_catalog": list(edge_catalog.columns),
            "node_catalog": list(node_catalog.columns),
        },
        "rows": {
            "summary": int(len(summary)),
            "edge_flows": int(len(edge_flows)),
            "service": int(len(service)),
            "edge_catalog": int(len(edge_catalog)),
            "node_catalog": int(len(node_catalog)),
        },
        "flow_conservation": {
            "status": "PASS",
            "cases": flow_conservation_cases,
            "max_internal_residual_units": max_internal_residual_units,
            "max_source_sink_residual_units": max_source_sink_residual_units,
        },
        "boundary": "capacity-constrained directed model on author-derived segment and node carriers; no engineering qualification is inferred; legacy pressure/cost details are omitted",
    }
    return NetworkResult(
        summary,
        edge_flows,
        service,
        audit,
        input_hashes,
        edge_catalog=edge_catalog,
        node_catalog=node_catalog,
        topology=topology,
    )


def load_network_outputs(root: Path) -> NetworkResult:
    """Load only persisted network-stage carriers for the analysis stage."""

    summary = read_csv(root, NETWORK_OUTPUTS["summary"], NETWORK_SUMMARY_COLUMNS)
    edge_flows = read_csv(root, NETWORK_OUTPUTS["edge_flows"], NETWORK_EDGE_FLOW_COLUMNS)
    service = read_csv(root, NETWORK_OUTPUTS["service"], NETWORK_SERVICE_COLUMNS)
    edge_catalog = read_csv(root, NETWORK_OUTPUTS["edge_catalog"], NETWORK_EDGE_CATALOG_COLUMNS)
    node_catalog = read_csv(root, NETWORK_OUTPUTS["node_catalog"], NETWORK_NODE_COLUMNS)
    payload = read_json(root, NETWORK_OUTPUTS["audit"])
    if not isinstance(payload, dict) or payload.get("stage") != "directed_network_flow":
        raise ValueError("network-stage audit is missing or has the wrong stage")
    input_hashes = payload.get("input_hashes")
    expected_hash_keys = {
        *(f"demand::{path}" for path in DEMAND_OUTPUTS.values()),
        *(f"network::{path}" for path in NETWORK_INPUTS.values()),
    }
    if not isinstance(input_hashes, dict) or set(input_hashes) != expected_hash_keys:
        raise ValueError("network-stage audit is missing input hashes")
    if any(not isinstance(value, str) or len(value) != 64 for value in input_hashes.values()):
        raise ValueError("network-stage audit contains invalid input hashes")
    raw_network_hashes = {
        str(key).removeprefix("network::"): str(value)
        for key, value in input_hashes.items()
        if str(key).startswith("network::")
    }
    topology = NetworkTopology(node_catalog, edge_catalog, raw_network_hashes)
    return NetworkResult(
        summary,
        edge_flows,
        service,
        payload,
        {str(key): str(value) for key, value in input_hashes.items()},
        edge_catalog=edge_catalog,
        node_catalog=node_catalog,
        topology=topology,
    )


def write_network_outputs(result: NetworkResult, root: Path) -> list[str]:
    """Persist the base directed-flow stage and reusable topology carriers."""

    output_dir = Path(root).resolve() / "data" / "processed" / "model_v01"
    if result.edge_catalog is None or result.node_catalog is None:
        raise ValueError("network result is missing reusable topology carriers")
    write_csv(result.summary, output_dir / "network_summary.csv")
    write_csv(result.edge_flows, output_dir / "network_edge_flows.csv")
    write_csv(result.service, output_dir / "network_service.csv")
    write_csv(result.edge_catalog, output_dir / "network_edge_catalog.csv")
    write_csv(result.node_catalog, output_dir / "network_node_catalog.csv")
    write_json(result.audit, output_dir / "network_model_audit.json")
    return list(NETWORK_OUTPUTS.values())


__all__ = [
    "CANDIDATE_INPUTS",
    "NETWORK_EDGE_CATALOG_COLUMNS",
    "NETWORK_EDGE_FLOW_COLUMNS",
    "NETWORK_INPUTS",
    "NETWORK_STAGE_INPUTS",
    "NETWORK_NODE_COLUMNS",
    "NETWORK_OUTPUTS",
    "NETWORK_SERVICE_COLUMNS",
    "NETWORK_SUMMARY_COLUMNS",
    "NetworkResult",
    "NetworkTopology",
    "haversine_km",
    "validate_flow_conservation",
    "load_network_outputs",
    "run_network",
    "write_network_outputs",
    "_read_candidate_links",
    "_read_segments",
    "_read_segment_tasks",
]
