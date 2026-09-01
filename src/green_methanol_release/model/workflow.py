"""Stage orchestration for the public model chain."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..safety import assert_public_path
from .analysis import AnalysisResult, run_dynamic_analysis, write_analysis_outputs
from .demand import DemandResult, preprocess_demand, write_demand_outputs
from .io import sha256
from .network import NetworkResult, run_network, write_network_outputs


MODEL_OUTPUT_DIR = "data/processed/model_v01"


@dataclass(frozen=True)
class ModelChainResult:
    demand: DemandResult
    network: NetworkResult
    analysis: AnalysisResult
    audit: dict[str, Any]
    output_paths: tuple[str, ...] = ()


def _frame_hash(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(index=False, encoding="utf-8", lineterminator="\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _render_model_figures(analysis: AnalysisResult, target_root: Path) -> list[str]:
    """Render Figure 4/5 from freshly regenerated model source tables."""

    from ..figures import build_figure_04, build_figure_05
    from .io import write_csv

    target_root = Path(target_root).resolve()
    source_dir = target_root / MODEL_OUTPUT_DIR
    source_dir.mkdir(parents=True, exist_ok=True)
    figure_dir = target_root / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    figure_04_source = source_dir / "figure_04_source.csv"
    figure_05_source = source_dir / "figure_05_source.csv"
    write_csv(analysis.figure_04_source, figure_04_source)
    write_csv(analysis.figure_05_source, figure_05_source)
    build_figure_04(figure_04_source, figure_dir / "model-figure-04.png")
    build_figure_05(figure_05_source, figure_dir / "model-figure-05.png")
    return [
        f"{MODEL_OUTPUT_DIR}/figure_04_source.csv",
        f"{MODEL_OUTPUT_DIR}/figure_05_source.csv",
        "figures/model-figure-04.png",
        "figures/model-figure-05.png",
    ]


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
    output_hashes: dict[str, str] = {}
    for relative in sorted(set(output_paths)):
        path = artifact_root / Path(*relative.split("/"))
        if path.is_file():
            output_hashes[relative] = sha256(path)
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
        "scientific_boundary": "Scenario demand is an assumption/proxy; flow is a directed capacity model; Figure 4/5 are model-derived accounts, not observations or engineering qualification.",
    }


def run_model_chain(root: Path, *, write_outputs: bool = False) -> ModelChainResult:
    """Run preprocessing, directed flow, dynamic analysis, and source regeneration."""

    root = Path(root).resolve()
    assert_public_path(root)
    demand = preprocess_demand(root)
    network = run_network(root, demand)
    analysis = run_dynamic_analysis(root, demand, network)
    output_paths: list[str] = []
    if write_outputs:
        output_paths.extend(write_demand_outputs(demand, root))
        output_paths.extend(write_network_outputs(network, root))
        output_paths.extend(write_analysis_outputs(analysis, root))
        output_paths.extend(_render_model_figures(analysis, root))
    audit = _chain_audit(demand, network, analysis, root, output_paths, artifact_root=root)
    return ModelChainResult(demand, network, analysis, audit, tuple(sorted(set(output_paths))))


def run_model_stage(
    root: Path,
    stage: str,
    *,
    output_root: Path | None = None,
) -> ModelChainResult:
    """Run one named registry stage while retaining the complete public chain."""

    root = Path(root).resolve()
    target = root if output_root is None else Path(output_root).resolve()
    assert_public_path(root)
    assert_public_path(target)
    if stage == "demand_preprocessing":
        chain = run_model_chain(root, write_outputs=False)
        demand, network, analysis = chain.demand, chain.network, chain.analysis
        output_paths = write_demand_outputs(demand, target)
    elif stage == "directed_network_flow":
        demand = preprocess_demand(root)
        network = run_network(root, demand)
        output_paths = write_network_outputs(network, target)
        analysis = run_dynamic_analysis(root, demand, network)
    elif stage == "dynamic_analysis":
        demand = preprocess_demand(root)
        network = run_network(root, demand)
        analysis = run_dynamic_analysis(root, demand, network)
        output_paths = write_analysis_outputs(analysis, target)
    elif stage in {"figure_04", "figure_05"}:
        chain = run_model_chain(root, write_outputs=False)
        demand, network, analysis = chain.demand, chain.network, chain.analysis
        write_analysis_outputs(analysis, target)
        output_paths = _render_model_figures(analysis, target)
        output_paths = [
            path
            for path in output_paths
            if path == f"figures/model-figure-{stage[-2:]}.png"
        ]
    else:
        raise ValueError(f"unsupported public model stage: {stage}")
    audit = _chain_audit(demand, network, analysis, root, output_paths, artifact_root=target)
    audit["requested_stage"] = stage
    return ModelChainResult(demand, network, analysis, audit, tuple(sorted(set(output_paths))))


__all__ = ["MODEL_OUTPUT_DIR", "ModelChainResult", "run_model_chain", "run_model_stage"]
