"""Demand and supply preprocessing from the public release carriers."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

import pandas as pd

from .config import (
    ANCHOR_YEARS,
    SCENARIOS,
    SECTORS,
    TIERS,
    YEARS,
    ModelConfig,
    load_config,
    pchip_interpolate,
)
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


DEMAND_INPUTS = {
    "demand_coefficients": "data/raw/demand/province_demand_corrected_product_coeff.csv",
    "aviation_origin": "data/raw/demand/province_origin_2024.csv",
    "supply_projection": "data/raw/supply/province_projection_nbs_generation.csv",
    "port_weights": "data/raw/official_sources/mot_2025_shipping_port_weights.csv",
    "city_master": "data/raw/city_topology_v01/city_master_2024.csv",
    "aviation_city_activity": "data/raw/city_topology_v01/aviation_refinery_city_activity.csv",
    "parameters": "config/model_parameters_v01.csv",
}
DEMAND_OUTPUTS = {
    "nodes": "data/processed/model_v01/demand_nodes.csv",
    "totals": "data/processed/model_v01/demand_totals.csv",
    "supply": "data/processed/model_v01/supply_nodes.csv",
    "components": "data/processed/model_v01/component_demand.csv",
    "audit": "data/processed/model_v01/demand_preprocessing_audit.json",
}

DEMAND_NODE_COLUMNS = (
    "scenario",
    "tier",
    "year",
    "sector",
    "province_key",
    "allocation_weight",
    "component_demand_10kt",
    "demand_10kt",
    "allocation_basis",
)
DEMAND_TOTAL_COLUMNS = ("scenario", "tier", "year", "demand_10kt", "scenario_semantics")
DEMAND_SUPPLY_COLUMNS = ("scenario", "tier", "year", "province_key", "supply_10kt")
DEMAND_COMPONENT_COLUMNS = (
    "scenario",
    "tier",
    "year",
    "sector",
    "composition_share",
    "component_demand_10kt",
    "scenario_semantics",
)


@dataclass(frozen=True)
class DemandResult:
    nodes: pd.DataFrame
    totals: pd.DataFrame
    supply: pd.DataFrame
    component_totals: pd.DataFrame
    audit: dict[str, Any]
    input_hashes: dict[str, str]


def _normalise_weights(frame: pd.DataFrame, province: str, value: str, label: str) -> dict[str, float]:
    values = frame[[province, value]].copy()
    values[province] = values[province].map(normalize_province)
    values[value] = pd.to_numeric(values[value], errors="coerce")
    if values[value].isna().any() or (values[value] < 0).any():
        raise ValueError(f"invalid non-negative weights for {label}")
    grouped = values.groupby(province, sort=True)[value].sum()
    total = float(grouped.sum())
    if not math.isfinite(total) or total <= 0:
        raise ValueError(f"{label} weights have no positive total")
    return {str(key): float(value) / total for key, value in grouped.items() if float(value) > 0}


def _coefficients(root: Path) -> tuple[dict[str, float], dict[str, float]]:
    frame = read_csv(root, DEMAND_INPUTS["demand_coefficients"])
    if frame.shape[1] < 13:
        raise ValueError("demand coefficient carrier has fewer than 13 columns")
    province = frame.iloc[:, 0].map(normalize_province)
    product_total = pd.to_numeric(frame.iloc[:, 11], errors="coerce")
    diesel = pd.to_numeric(frame.iloc[:, 8], errors="coerce")
    if product_total.isna().any() or diesel.isna().any():
        raise ValueError("demand coefficient carrier has malformed numeric values")
    data = pd.DataFrame({"province_key": province, "product_total": product_total, "diesel": diesel})
    product = _normalise_weights(data, "province_key", "product_total", "product-demand proxy")
    trucking = _normalise_weights(data, "province_key", "diesel", "diesel-demand proxy")
    return product, trucking


def _aviation_weights(root: Path) -> dict[str, float]:
    activity = read_csv(root, DEMAND_INPUTS["aviation_city_activity"])
    city = read_csv(
        root,
        DEMAND_INPUTS["city_master"],
        (
            "city_code",
            "city_name",
            "province_code",
            "province_name",
            "admin_type",
            "longitude",
            "latitude",
            "valid_from",
            "valid_to",
            "source_id",
        ),
    )
    activity_values = activity[["city_code", "activity_value"]].copy()
    activity_values["city_code"] = pd.to_numeric(activity_values["city_code"], errors="coerce")
    activity_values["activity_value"] = pd.to_numeric(activity_values["activity_value"], errors="coerce")
    if activity_values.isna().any().any() or (activity_values["activity_value"] < 0).any():
        raise ValueError("aviation city activity has malformed numeric values")
    city_lookup = city[["city_code", "province_name"]].copy()
    city_lookup["city_code"] = pd.to_numeric(city_lookup["city_code"], errors="coerce")
    merged = activity_values.merge(city_lookup, on="city_code", how="left", validate="one_to_one")
    if merged["province_name"].isna().any():
        raise ValueError("aviation city activity contains an unmapped city")
    merged["province_key"] = merged["province_name"].map(normalize_province)
    return _normalise_weights(merged, "province_key", "activity_value", "aviation refinery-city proxy")


def _port_weights(root: Path) -> dict[str, float]:
    frame = read_csv(
        root,
        DEMAND_INPUTS["port_weights"],
        (
            "province",
            "province_key",
            "cargo_throughput_10kt",
            "source_indicator",
            "source_unit",
            "source_agency",
            "source_page_url",
            "source_pdf_url",
            "accessed_date",
            "share",
            "rounding_diff_vs_coastal_total_10kt",
        ),
    )
    return _normalise_weights(frame, "province_key", "share", "port-throughput proxy")


def _origin_weights(root: Path) -> dict[str, float]:
    frame = read_csv(
        root,
        DEMAND_INPUTS["aviation_origin"],
        ("origin_province", "records", "ask_km", "seats", "ask_share"),
    )
    frame = frame.rename(columns={"origin_province": "province_key"})
    return _normalise_weights(frame, "province_key", "ask_share", "aviation-origin proxy")


def _build_sector_paths(config: ModelConfig) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for sector in SECTORS:
        for tier in TIERS:
            adoption = pchip_interpolate(
                ANCHOR_YEARS,
                tuple(config.adoption_share[(sector, tier, year)] for year in ANCHOR_YEARS),
                YEARS,
            )
            route = pchip_interpolate(
                ANCHOR_YEARS,
                tuple(config.route_share[(sector, tier, year)] for year in ANCHOR_YEARS),
                YEARS,
            )
            for year, adoption_value, route_value in zip(YEARS, adoption, route, strict=True):
                demand = (
                    config.sector_activity_10kt[sector]
                    * adoption_value
                    * route_value
                    * config.conversion_factor[sector]
                )
                rows.append(
                    {
                        "sector": sector,
                        "tier": tier,
                        "year": year,
                        "activity_10kt": config.sector_activity_10kt[sector],
                        "adoption_share": adoption_value,
                        "methanol_route_share": route_value,
                        "conversion_factor": config.conversion_factor[sector],
                        "sector_demand_10kt": demand,
                    }
                )
    return sorted_frame(pd.DataFrame(rows), ("sector", "tier", "year"))


def _scenario_components(paths: pd.DataFrame, config: ModelConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    lookup = paths.set_index(["sector", "tier", "year"])["sector_demand_10kt"]
    total_rows: list[dict[str, Any]] = []
    component_rows: list[dict[str, Any]] = []
    for tier in TIERS:
        for year in YEARS:
            sector_values = {sector: float(lookup.loc[(sector, tier, year)]) for sector in SECTORS}
            s5_total = math.fsum(sector_values.values())
            for scenario in SCENARIOS:
                if scenario in {"S1", "S2", "S3", "S4"}:
                    selected = SECTORS[int(scenario[1]) - 1]
                    shares = {sector: float(sector == selected) for sector in SECTORS}
                    semantics = "single-sector dynamic demand"
                elif scenario == "S5":
                    shares = {
                        sector: (sector_values[sector] / s5_total if s5_total else 0.0)
                        for sector in SECTORS
                    }
                    semantics = "exact sum of S1-S4; no second weighting"
                else:
                    shares = {
                        sector: config.structural_share[(scenario, sector)] for sector in SECTORS
                    }
                    semantics = "fixed composition at S5 total"
                total = math.fsum(sector_values[sector] * shares[sector] for sector in SECTORS)
                total_rows.append(
                    {
                        "scenario": scenario,
                        "tier": tier,
                        "year": year,
                        "demand_10kt": total,
                        "scenario_semantics": semantics,
                    }
                )
                for sector in SECTORS:
                    component_rows.append(
                        {
                            "scenario": scenario,
                            "tier": tier,
                            "year": year,
                            "sector": sector,
                            "composition_share": shares[sector],
                            "component_demand_10kt": sector_values[sector] * shares[sector],
                            "scenario_semantics": semantics,
                        }
                    )
    return (
        sorted_frame(pd.DataFrame(total_rows), ("scenario", "tier", "year")),
        sorted_frame(pd.DataFrame(component_rows), ("scenario", "tier", "year", "sector")),
    )


def _supply_nodes(root: Path, config: ModelConfig) -> pd.DataFrame:
    frame = read_csv(
        root,
        DEMAND_INPUTS["supply_projection"],
        (
            "province",
            "province_std",
            "year",
            "scenario",
            "projected_curtailed_wind_TWh",
            "projected_curtailed_solar_TWh",
            "projected_curtailed_total_TWh",
            "methanol_supply_Mt",
            "h2_required_Mt",
            "co2_required_Mt",
            "allocation_basis",
        ),
    )
    frame["province_key"] = frame["province_std"].map(normalize_province)
    frame["year"] = pd.to_numeric(frame["year"], errors="raise").astype(int)
    frame["methanol_supply_Mt"] = pd.to_numeric(frame["methanol_supply_Mt"], errors="raise")
    if frame["methanol_supply_Mt"].isna().any() or (frame["methanol_supply_Mt"] < 0).any():
        raise ValueError("supply projection has malformed methanol_supply_Mt")
    rows: list[dict[str, Any]] = []
    for tier in TIERS:
        supply_scenario = config.supply_scenario[tier]
        selected = frame[frame["scenario"].eq(supply_scenario)].copy()
        if selected.empty:
            raise ValueError(f"supply projection missing scenario {supply_scenario!r}")
        grouped = selected.groupby(["province_key", "year"], sort=True)["methanol_supply_Mt"].sum()
        for (province, year), value in grouped.items():
            rows.append(
                {
                    "scenario": supply_scenario,
                    "tier": tier,
                    "year": int(year),
                    "province_key": str(province),
                    "supply_10kt": float(value) * 100.0,
                }
            )
    return sorted_frame(pd.DataFrame(rows), ("tier", "year", "province_key"))


def preprocess_demand(root: Path) -> DemandResult:
    """Build scenario demand nodes and tier-mapped supply nodes from public data."""

    root = Path(root).resolve()
    config = load_config(root)
    product_weights, diesel_weights = _coefficients(root)
    aviation_weights = _aviation_weights(root)
    port_weights = _port_weights(root)
    # The aviation-origin carrier is validated and retained as a sensitivity
    # proxy; refinery-city activity is the primary C allocation carrier.
    origin_weights = _origin_weights(root)
    weights = {"A": port_weights, "B": product_weights, "C": aviation_weights, "D": diesel_weights}
    paths = _build_sector_paths(config)
    totals, component_totals = _scenario_components(paths, config)
    rows: list[dict[str, Any]] = []
    for component in component_totals.itertuples(index=False):
        for province, weight in sorted(weights[component.sector].items()):
            rows.append(
                {
                    "scenario": component.scenario,
                    "tier": component.tier,
                    "year": int(component.year),
                    "sector": component.sector,
                    "province_key": province,
                    "allocation_weight": weight,
                    "component_demand_10kt": float(component.component_demand_10kt),
                    "demand_10kt": float(component.component_demand_10kt) * weight,
                    "allocation_basis": {
                        "A": "official port-throughput share",
                        "B": "corrected product-demand proxy",
                        "C": "documented refinery-city activity proxy",
                        "D": "corrected diesel-demand proxy",
                    }[component.sector],
                }
            )
    nodes = sorted_frame(pd.DataFrame(rows), ("scenario", "tier", "year", "sector", "province_key"))
    supply = _supply_nodes(root, config)
    # Verify the main closure with stable summation rather than depending on
    # pandas' input-order reduction.
    node_totals = nodes.groupby(["scenario", "tier", "year"], sort=True)["demand_10kt"].sum()
    total_lookup = totals.set_index(["scenario", "tier", "year"])["demand_10kt"]
    if (node_totals.sort_index() - total_lookup.sort_index()).abs().max() > 1e-8:
        raise RuntimeError("demand preprocessing node allocation does not close")
    input_hashes = hashes_for_paths(root, DEMAND_INPUTS.values())
    audit = {
        "status": "PASS",
        "stage": "demand_preprocessing",
        "years": list(YEARS),
        "tiers": list(TIERS),
        "scenarios": list(SCENARIOS),
        "input_paths": sorted(DEMAND_INPUTS.values()),
        "input_hashes": input_hashes,
        "schema": {
            "demand_nodes": list(nodes.columns),
            "demand_totals": list(totals.columns),
            "supply_nodes": list(supply.columns),
            "component_totals": list(component_totals.columns),
        },
        "rows": {
            "demand_nodes": int(len(nodes)),
            "demand_totals": int(len(totals)),
            "supply_nodes": int(len(supply)),
            "component_totals": int(len(component_totals)),
        },
        "proxy_boundaries": {
            "aviation_origin": "validated as a public sensitivity proxy; not used as the primary city allocation",
            "city_activity": "documented refinery-city activity proxy; not measured methanol demand",
        },
    }
    return DemandResult(nodes, totals, supply, component_totals, audit, input_hashes)


def load_demand_outputs(root: Path) -> DemandResult:
    """Load only the persisted demand-stage carriers for downstream stages."""

    nodes = read_csv(root, DEMAND_OUTPUTS["nodes"], DEMAND_NODE_COLUMNS)
    totals = read_csv(root, DEMAND_OUTPUTS["totals"], DEMAND_TOTAL_COLUMNS)
    supply = read_csv(root, DEMAND_OUTPUTS["supply"], DEMAND_SUPPLY_COLUMNS)
    components = read_csv(root, DEMAND_OUTPUTS["components"], DEMAND_COMPONENT_COLUMNS)
    payload = read_json(root, DEMAND_OUTPUTS["audit"])
    if not isinstance(payload, dict) or payload.get("stage") != "demand_preprocessing":
        raise ValueError("demand-stage audit is missing or has the wrong stage")
    input_hashes = payload.get("input_hashes")
    if not isinstance(input_hashes, dict) or set(input_hashes) != set(DEMAND_INPUTS.values()):
        raise ValueError("demand-stage audit input hashes do not match public demand inputs")
    if any(not isinstance(value, str) or len(value) != 64 for value in input_hashes.values()):
        raise ValueError("demand-stage audit contains invalid input hashes")
    return DemandResult(
        nodes,
        totals,
        supply,
        components,
        payload,
        {str(key): str(value) for key, value in input_hashes.items()},
    )


def write_demand_outputs(result: DemandResult, root: Path) -> list[str]:
    """Persist the preprocessing stage to its release-relative carrier paths."""

    output_dir = Path(root).resolve() / "data" / "processed" / "model_v01"
    write_csv(result.nodes, output_dir / "demand_nodes.csv")
    write_csv(result.totals, output_dir / "demand_totals.csv")
    write_csv(result.supply, output_dir / "supply_nodes.csv")
    write_csv(result.component_totals, output_dir / "component_demand.csv")
    write_json(result.audit, output_dir / "demand_preprocessing_audit.json")
    return [
        "data/processed/model_v01/demand_nodes.csv",
        "data/processed/model_v01/demand_totals.csv",
        "data/processed/model_v01/supply_nodes.csv",
        "data/processed/model_v01/component_demand.csv",
        "data/processed/model_v01/demand_preprocessing_audit.json",
    ]


__all__ = [
    "DEMAND_COMPONENT_COLUMNS",
    "DEMAND_INPUTS",
    "DEMAND_NODE_COLUMNS",
    "DEMAND_OUTPUTS",
    "DEMAND_SUPPLY_COLUMNS",
    "DEMAND_TOTAL_COLUMNS",
    "DemandResult",
    "load_demand_outputs",
    "preprocess_demand",
    "write_demand_outputs",
]
