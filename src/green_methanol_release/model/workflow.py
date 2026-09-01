"""Stage orchestration for the public model chain."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

import pandas as pd

from ..contracts import safe_relative_path
from ..safety import assert_public_path
from .analysis import (
    ANALYSIS_FIGURE_SOURCES,
    ANALYSIS_INPUTS,
    AnalysisResult,
    load_analysis_outputs,
    run_dynamic_analysis,
    write_analysis_outputs,
)
from .demand import (
    DEMAND_INPUTS,
    DemandResult,
    load_demand_outputs,
    preprocess_demand,
    write_demand_outputs,
)
from .io import CSV_FLOAT_FORMAT, read_csv, sha256, verify_registered_hashes, write_csv
from .network import (
    NETWORK_INPUTS,
    NETWORK_STAGE_INPUTS,
    NetworkResult,
    load_network_outputs,
    run_network,
    write_network_outputs,
)


MODEL_OUTPUT_DIR = "data/processed/model_v01"


@dataclass(frozen=True)
class ModelChainResult:
    demand: DemandResult | None
    network: NetworkResult | None
    analysis: AnalysisResult | None
    audit: dict[str, Any]
    output_paths: tuple[str, ...] = ()


_STAGE_INPUTS = {
    "demand_preprocessing": tuple(DEMAND_INPUTS.values()),
    "directed_network_flow": tuple(NETWORK_STAGE_INPUTS.values()),
    "dynamic_analysis": tuple(ANALYSIS_INPUTS.values()),
    "figure_04": (ANALYSIS_FIGURE_SOURCES["figure_04"],),
    "figure_05": (ANALYSIS_FIGURE_SOURCES["figure_05"],),
}


def _validate_stage_inputs(
    root: Path,
    stage: str,
    input_paths: list[str] | tuple[str, ...] | None,
) -> tuple[str, ...]:
    expected = tuple(_STAGE_INPUTS[stage])
    provided = expected if input_paths is None else tuple(
        str(value).replace("\\", "/") for value in input_paths
    )
    normalized: list[str] = []
    for value in provided:
        try:
            relative = safe_relative_path(value)
            assert_public_path(Path(value))
        except ValueError as exc:
            raise ValueError(f"{stage} input path is not release-relative: {value!r}") from exc
        normalized.append(relative.as_posix())
    if len(normalized) != len(set(normalized)) or sorted(normalized) != sorted(expected):
        raise ValueError(
            f"{stage} inputs must match the registered stage contract: "
            f"expected={sorted(expected)}, provided={sorted(normalized)}"
        )

    if stage == "demand_preprocessing":
        verify_registered_hashes(root, DEMAND_INPUTS.values())
    elif stage == "directed_network_flow":
        verify_registered_hashes(root, NETWORK_INPUTS.values())
    elif stage == "dynamic_analysis":
        verify_registered_hashes(
            root,
            (
                ANALYSIS_INPUTS["candidate_links"],
                ANALYSIS_INPUTS["selected_plans"],
                ANALYSIS_INPUTS["parameters"],
            ),
        )
    return tuple(normalized)


def _frame_hash(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(
        index=False,
        encoding="utf-8",
        lineterminator="\n",
        float_format=CSV_FLOAT_FORMAT,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _render_model_figures(analysis: AnalysisResult, target_root: Path) -> list[str]:
    """Render both model figures from the persisted analysis source tables."""

    from ..figures import build_figure_04, build_figure_05

    target_root = Path(target_root).resolve()
    source_dir = target_root / MODEL_OUTPUT_DIR
    source_dir.mkdir(parents=True, exist_ok=True)
    figure_dir = target_root / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    figure_04_source = source_dir / "figure_04_source.csv"
    figure_05_source = source_dir / "figure_05_source.csv"
    if not figure_04_source.is_file() or not figure_05_source.is_file():
        raise ValueError("analysis source carriers must be persisted before figure rendering")
    build_figure_04(figure_04_source, figure_dir / "model-figure-04.png")
    build_figure_05(figure_05_source, figure_dir / "model-figure-05.png")
    return [
        f"{MODEL_OUTPUT_DIR}/figure_04_source.csv",
        f"{MODEL_OUTPUT_DIR}/figure_05_source.csv",
        "figures/model-figure-04.png",
        "figures/model-figure-05.png",
    ]


def _render_one_model_figure(stage: str, root: Path, target_root: Path) -> str:
    """Render one figure from an existing analysis source without side effects."""

    from ..figures import build_figure_04, build_figure_05

    if stage not in {"figure_04", "figure_05"}:
        raise ValueError(f"unsupported model figure stage: {stage}")
    source = root / Path(*ANALYSIS_FIGURE_SOURCES[stage].split("/"))
    if not source.is_file():
        raise ValueError(f"analysis source is missing for {stage}: {source}")
    target = Path(target_root).resolve() / "figures" / f"model-figure-{stage[-2:]}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    builder = build_figure_04 if stage == "figure_04" else build_figure_05
    builder(source, target)
    return f"figures/model-figure-{stage[-2:]}.png"


def _hash_output_paths(output_paths: list[str], artifact_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in sorted(set(output_paths)):
        path = Path(artifact_root).resolve() / Path(*relative.split("/"))
        if path.is_file():
            hashes[relative] = sha256(path)
    return hashes


def _chain_audit(
    demand: DemandResult,
    network: NetworkResult,
    analysis: AnalysisResult,
    root: Path,
    output_paths: list[str],
    *,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    artifact_root = root if artifact_root is None else Path(artifact_root).resolve()
    output_hashes = _hash_output_paths(output_paths, artifact_root)
    if not output_hashes:
        output_hashes = {
            "in-memory:demand_nodes": _frame_hash(demand.nodes),
            "in-memory:network_summary": _frame_hash(network.summary),
            "in-memory:regional_accounts": _frame_hash(analysis.regional_accounts),
            "in-memory:figure_04_source": _frame_hash(analysis.figure_04_source),
            "in-memory:figure_05_source": _frame_hash(analysis.figure_05_source),
        }
    return {
        "status": "PASS",
        "workflow": "public_model_chain",
        "stages": {
            "demand_preprocessing": demand.audit["status"],
            "directed_network_flow": network.audit["status"],
            "dynamic_analysis": analysis.audit["status"],
            "figure_source_regeneration": "PASS",
        },
        "input_hashes": {
            **demand.input_hashes,
            **network.input_hashes,
            **analysis.input_hashes,
        },
        "output_hashes": output_hashes,
        "schema": {
            "demand_nodes": list(demand.nodes.columns),
            "network_edge_flows": list(network.edge_flows.columns),
            "regional_accounts": list(analysis.regional_accounts.columns),
            "figure_04_source": list(analysis.figure_04_source.columns),
            "figure_05_source": list(analysis.figure_05_source.columns),
        },
        "rows": {
            "demand_nodes": int(len(demand.nodes)),
            "network_summary": int(len(network.summary)),
            "network_edge_flows": int(len(network.edge_flows)),
            "regional_accounts": int(len(analysis.regional_accounts)),
            "figure_04_source": int(len(analysis.figure_04_source)),
            "figure_05_source": int(len(analysis.figure_05_source)),
        },
        "scientific_boundary": "Scenario demand is an assumption/proxy; flow is a directed capacity model; model Figures 4/5 are diagnostic/model-derived outputs, not formal manuscript figures, observations, or engineering qualification; legacy pressure/cost details are omitted.",
    }


def _stage_audit(stage: str, payload: dict[str, Any], output_paths: list[str], target: Path) -> dict[str, Any]:
    audit = dict(payload)
    audit["requested_stage"] = stage
    audit["output_hashes"] = _hash_output_paths(output_paths, target)
    return audit


def run_model_chain(root: Path, *, write_outputs: bool = False) -> ModelChainResult:
    """Run preprocessing, directed flow, dynamic analysis, and figure sources."""

    root = Path(root).resolve()
    assert_public_path(root)
    demand = preprocess_demand(root)
    output_paths: list[str] = []
    if write_outputs:
        output_paths.extend(write_demand_outputs(demand, root))
        # Continue from the persisted carrier so the convenience chain has
        # byte-for-byte parity with the registered stage workflow.
        demand = load_demand_outputs(root)
    network = run_network(root, demand)
    if write_outputs:
        output_paths.extend(write_network_outputs(network, root))
        network = load_network_outputs(root)
    analysis = run_dynamic_analysis(root, demand, network)
    if write_outputs:
        output_paths.extend(write_analysis_outputs(analysis, root))
        analysis = load_analysis_outputs(root)
        output_paths.extend(_render_model_figures(analysis, root))
    audit = _chain_audit(demand, network, analysis, root, output_paths, artifact_root=root)
    return ModelChainResult(demand, network, analysis, audit, tuple(sorted(set(output_paths))))


def run_model_stage(
    root: Path,
    stage: str,
    *,
    output_root: Path | None = None,
    input_paths: list[str] | tuple[str, ...] | None = None,
) -> ModelChainResult:
    """Run one registered stage and only write that stage's artifacts."""

    root = Path(root).resolve()
    target = root if output_root is None else Path(output_root).resolve()
    assert_public_path(root)
    assert_public_path(target)
    if stage not in _STAGE_INPUTS:
        raise ValueError(f"unsupported public model stage: {stage}")
    _validate_stage_inputs(root, stage, input_paths)
    if stage == "demand_preprocessing":
        demand = preprocess_demand(root)
        output_paths = write_demand_outputs(demand, target)
        audit = _stage_audit(stage, demand.audit, output_paths, target)
        return ModelChainResult(demand, None, None, audit, tuple(sorted(set(output_paths))))
    if stage == "directed_network_flow":
        demand = load_demand_outputs(root)
        network = run_network(root, demand)
        output_paths = write_network_outputs(network, target)
        audit = _stage_audit(stage, network.audit, output_paths, target)
        return ModelChainResult(demand, network, None, audit, tuple(sorted(set(output_paths))))
    if stage == "dynamic_analysis":
        demand = load_demand_outputs(root)
        network = load_network_outputs(root)
        analysis = run_dynamic_analysis(root, demand, network)
        output_paths = write_analysis_outputs(analysis, target)
        audit = _stage_audit(stage, analysis.audit, output_paths, target)
        return ModelChainResult(demand, network, analysis, audit, tuple(sorted(set(output_paths))))
    if stage in {"figure_04", "figure_05"}:
        load_analysis_outputs(root)
        source_relative = ANALYSIS_FIGURE_SOURCES[stage]
        source = read_csv(root, source_relative)
        source_hash = sha256(root / Path(*source_relative.split("/")))
        output_path = _render_one_model_figure(stage, root, target)
        figure_04 = source if stage == "figure_04" else pd.DataFrame()
        figure_05 = source if stage == "figure_05" else pd.DataFrame()
        analysis = AnalysisResult(
            pd.DataFrame(),
            pd.DataFrame(),
            figure_04,
            figure_05,
            {
                "status": "PASS",
                "stage": stage,
                "input_paths": [source_relative],
                "input_hashes": {source_relative: source_hash},
            },
            {source_relative: source_hash},
        )
        audit = _stage_audit(stage, analysis.audit, [output_path], target)
        return ModelChainResult(
            None,
            None,
            analysis,
            audit,
            (output_path,),
        )
    raise ValueError(f"unsupported public model stage: {stage}")


__all__ = ["MODEL_OUTPUT_DIR", "ModelChainResult", "run_model_chain", "run_model_stage"]
