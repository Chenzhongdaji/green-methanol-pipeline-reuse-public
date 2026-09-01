"""Versioned model-parameter loading for the public release."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from .io import finite_float, read_csv


CONFIG_COLUMNS = (
    "parameter",
    "sector",
    "tier",
    "year",
    "scenario",
    "value",
    "unit",
    "notes",
)
SECTORS = ("A", "B", "C", "D")
TIERS = ("low", "mid", "high")
SCENARIOS = tuple(f"S{index}" for index in range(1, 9))
YEARS = tuple(range(2025, 2061, 5))
ANCHOR_YEARS = (2025, 2030, 2060)


@dataclass(frozen=True)
class ModelConfig:
    sector_activity_10kt: dict[str, float]
    conversion_factor: dict[str, float]
    adoption_share: dict[tuple[str, str, int], float]
    route_share: dict[tuple[str, str, int], float]
    structural_share: dict[tuple[str, str], float]
    supply_scenario: dict[str, str]
    capacity_basis: str
    flow_scale: int
    capacity_relaxation_factor: float
    transport_cost_per_km: float


def _required_single(
    frame: pd.DataFrame,
    parameter: str,
    *,
    key_columns: Iterable[str] = (),
) -> dict[tuple[str, ...], float]:
    subset = frame[frame["parameter"].eq(parameter)].copy()
    keys = tuple(key_columns)
    if subset.empty:
        raise ValueError(f"model configuration is missing {parameter!r}")
    if subset.duplicated(list(keys)).any():
        raise ValueError(f"model configuration repeats {parameter!r} keys")
    values: dict[tuple[str, ...], float] = {}
    for row in subset.itertuples(index=False):
        values[tuple(str(getattr(row, key)).strip() for key in keys)] = finite_float(
            getattr(row, "value"), parameter
        )
    return values


def load_config(root: Path, relative: str = "config/model_parameters_v01.csv") -> ModelConfig:
    """Load and validate the fixed model-parameter table."""

    frame = read_csv(root, relative, CONFIG_COLUMNS)
    frame = frame.copy()
    for field in ("parameter", "sector", "tier", "year", "scenario", "unit", "notes"):
        frame[field] = frame[field].fillna("").astype(str).str.strip()
    frame["year"] = frame["year"].replace({"": "0"})
    frame["year"] = pd.to_numeric(frame["year"], errors="raise").astype(int)
    numeric_rows = ~frame["parameter"].eq("capacity_basis")
    frame["value"] = frame["value"].astype(object)
    frame.loc[numeric_rows, "value"] = pd.to_numeric(
        frame.loc[numeric_rows, "value"], errors="raise"
    )

    activity = _required_single(frame, "sector_activity_10kt", key_columns=("sector",))
    conversion = _required_single(frame, "conversion_factor", key_columns=("sector",))
    adoption_raw = _required_single(
        frame,
        "adoption_share",
        key_columns=("sector", "tier", "year"),
    )
    route_raw = _required_single(
        frame,
        "route_share",
        key_columns=("sector", "tier", "year"),
    )
    structural_raw = _required_single(
        frame,
        "structural_share",
        key_columns=("scenario", "sector"),
    )
    supply_raw = _required_single(frame, "supply_scenario", key_columns=("tier",))
    adoption_raw = {
        (key[0], key[1], int(key[2])): value for key, value in adoption_raw.items()
    }
    route_raw = {
        (key[0], key[1], int(key[2])): value for key, value in route_raw.items()
    }
    # ``supply_scenario`` is text rather than numeric, so load it separately.
    supply_rows = frame[frame["parameter"].eq("supply_scenario")]
    supply_scenario: dict[str, str] = {}
    for row in supply_rows.itertuples(index=False):
        tier = str(row.tier).strip()
        scenario = str(row.scenario).strip()
        if tier in supply_scenario or not scenario:
            raise ValueError("model configuration has an invalid supply_scenario mapping")
        supply_scenario[tier] = scenario
    # The numeric helper above intentionally verifies that the rows are present;
    # the text mapping is what the model uses.
    del supply_raw

    def scalar(parameter: str, default: float | None = None) -> float:
        subset = frame[frame["parameter"].eq(parameter)]
        if subset.empty:
            if default is None:
                raise ValueError(f"model configuration is missing {parameter!r}")
            return default
        if len(subset) != 1:
            raise ValueError(f"model configuration repeats scalar {parameter!r}")
        return finite_float(subset.iloc[0]["value"], parameter)

    if {key[0] for key in activity} != set(SECTORS) or {key[0] for key in conversion} != set(SECTORS):
        raise ValueError("model configuration must define all four sector parameters")
    expected_anchor_keys = {
        (sector, tier, year)
        for sector in SECTORS
        for tier in TIERS
        for year in ANCHOR_YEARS
    }
    if set(adoption_raw) != expected_anchor_keys or set(route_raw) != expected_anchor_keys:
        raise ValueError("model configuration anchor grid is incomplete")
    for key, value in {**adoption_raw, **route_raw}.items():
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"model configuration share is outside [0,1]: {key}")
    expected_structural_keys = {
        (scenario, sector)
        for scenario in ("S6", "S7", "S8")
        for sector in SECTORS
    }
    if set(structural_raw) != expected_structural_keys:
        raise ValueError("model configuration structural-share grid is incomplete")
    for scenario in ("S6", "S7", "S8"):
        total = sum(structural_raw[(scenario, sector)] for sector in SECTORS)
        if abs(total - 1.0) > 1e-12:
            raise ValueError(f"structural shares for {scenario} do not sum to one")
    if set(supply_scenario) != set(TIERS):
        raise ValueError("model configuration must map every tier to a supply scenario")

    basis_rows = frame[frame["parameter"].eq("capacity_basis")]
    if len(basis_rows) != 1:
        raise ValueError("model configuration must define one capacity_basis")
    capacity_basis = str(basis_rows.iloc[0]["value"]).strip()
    if capacity_basis != "same_pipeline_task_10kt":
        raise ValueError("capacity_basis must select same_pipeline_task_10kt")

    flow_scale = int(round(scalar("flow_scale")))
    if flow_scale <= 0:
        raise ValueError("flow_scale must be positive")
    return ModelConfig(
        sector_activity_10kt={key[0]: value for key, value in activity.items()},
        conversion_factor={key[0]: value for key, value in conversion.items()},
        adoption_share=adoption_raw,
        route_share=route_raw,
        structural_share=structural_raw,
        supply_scenario=supply_scenario,
        capacity_basis=capacity_basis,
        flow_scale=flow_scale,
        capacity_relaxation_factor=scalar("capacity_relaxation_factor", 1.1),
        transport_cost_per_km=scalar("transport_cost_per_km", 1.0),
    )


def pchip_interpolate(
    anchor_years: tuple[int, ...],
    anchor_values: tuple[float, ...],
    target_years: tuple[int, ...],
) -> list[float]:
    """Fritsch-Carlson monotone cubic interpolation without extrapolation."""

    if len(anchor_years) != len(anchor_values) or len(anchor_years) < 2:
        raise ValueError("PCHIP anchors must have equal length and at least two points")
    if any(right <= left for left, right in zip(anchor_years, anchor_years[1:])):
        raise ValueError("PCHIP anchor years must be strictly increasing")
    if min(target_years) < min(anchor_years) or max(target_years) > max(anchor_years):
        raise ValueError("PCHIP target years cannot extrapolate")
    x = [float(item) for item in anchor_years]
    y = [float(item) for item in anchor_values]
    h = [right - left for left, right in zip(x, x[1:])]
    delta = [(right - left) / width for left, right, width in zip(y, y[1:], h)]
    slopes = [0.0] * len(y)
    if len(y) == 2:
        slopes = [delta[0], delta[0]]
    else:
        for index in range(1, len(y) - 1):
            left = delta[index - 1]
            right = delta[index]
            if left == 0.0 or right == 0.0 or left * right < 0.0:
                slopes[index] = 0.0
            else:
                w1 = 2.0 * h[index] + h[index - 1]
                w2 = h[index] + 2.0 * h[index - 1]
                slopes[index] = (w1 + w2) / (w1 / left + w2 / right)
        left = ((2.0 * h[0] + h[1]) * delta[0] - h[0] * delta[1]) / (h[0] + h[1])
        if left * delta[0] <= 0.0:
            left = 0.0
        elif delta[0] * delta[1] < 0.0 and abs(left) > 3.0 * abs(delta[0]):
            left = 3.0 * delta[0]
        slopes[0] = left
        right = ((2.0 * h[-1] + h[-2]) * delta[-1] - h[-1] * delta[-2]) / (h[-1] + h[-2])
        if right * delta[-1] <= 0.0:
            right = 0.0
        elif delta[-1] * delta[-2] < 0.0 and abs(right) > 3.0 * abs(delta[-1]):
            right = 3.0 * delta[-1]
        slopes[-1] = right

    values: list[float] = []
    for target in target_years:
        if target in anchor_years:
            values.append(y[anchor_years.index(target)])
            continue
        index = max(0, min(len(h) - 1, next(i for i in range(len(h)) if target < anchor_years[i + 1])))
        width = x[index + 1] - x[index]
        z = (target - x[index]) / width
        h00 = 2.0 * z**3 - 3.0 * z**2 + 1.0
        h10 = z**3 - 2.0 * z**2 + z
        h01 = -2.0 * z**3 + 3.0 * z**2
        h11 = z**3 - z**2
        values.append(
            max(
                0.0,
                min(
                    1.0,
                    h00 * y[index]
                    + h10 * width * slopes[index]
                    + h01 * y[index + 1]
                    + h11 * width * slopes[index + 1],
                ),
            )
        )
    return values


__all__ = [
    "ANCHOR_YEARS",
    "CONFIG_COLUMNS",
    "ModelConfig",
    "SCENARIOS",
    "SECTORS",
    "TIERS",
    "YEARS",
    "load_config",
    "pchip_interpolate",
]
