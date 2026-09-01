from __future__ import annotations

from pathlib import Path

import pytest

from green_methanol_release.inventory import load_dataset_registry, load_output_registry
from green_methanol_release.model.analysis import ANALYSIS_INPUTS, ANALYSIS_OUTPUTS
from green_methanol_release.model.demand import DEMAND_INPUTS, DEMAND_OUTPUTS
from green_methanol_release.model.network import NETWORK_INPUTS, NETWORK_OUTPUTS
from green_methanol_release.model import workflow as workflow_module
from green_methanol_release.model.workflow import MODEL_OUTPUT_DIR, run_model_stage


ROOT = Path(__file__).resolve().parents[1]


def _payloads(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_registered_model_stages_have_exact_input_and_output_closures():
    datasets = {
        row["dataset_id"]: row["public_path"]
        for row in load_dataset_registry(ROOT / "data" / "dataset_registry.csv")
    }
    outputs = {
        row["output_id"]: row
        for row in load_output_registry(ROOT / "data" / "output_registry.csv")
    }
    expected_inputs = {
        "model-preprocess": set(DEMAND_INPUTS.values()),
        "model-network": set(
            (*DEMAND_OUTPUTS.values(), *NETWORK_INPUTS.values())
        ),
        "model-analysis": set(ANALYSIS_INPUTS.values()),
        "model-figure-04": {ANALYSIS_OUTPUTS["figure_04_source"]},
        "model-figure-05": {ANALYSIS_OUTPUTS["figure_05_source"]},
    }
    expected_outputs = {
        "model-preprocess": set(DEMAND_OUTPUTS.values()),
        "model-network": set(NETWORK_OUTPUTS.values()),
        "model-analysis": set(ANALYSIS_OUTPUTS.values()),
        "model-figure-04": {"figures/model-figure-04.png"},
        "model-figure-05": {"figures/model-figure-05.png"},
    }
    for output_id in expected_inputs:
        row = outputs[output_id]
        input_paths = {datasets[dataset_id] for dataset_id in row["input_dataset_ids"].split(";")}
        output_paths = {row["expected_artifact"]}
        output_paths.update(
            item for item in row["secondary_artifacts"].split(";") if item
        )
        assert input_paths == expected_inputs[output_id]
        assert output_paths == expected_outputs[output_id]


def test_demand_stage_does_not_execute_network_or_analysis(monkeypatch, tmp_path: Path):
    def fail(*args, **kwargs):
        raise AssertionError("demand stage must not execute downstream stages")

    monkeypatch.setattr(workflow_module, "run_network", fail)
    monkeypatch.setattr(workflow_module, "run_dynamic_analysis", fail)
    run_model_stage(ROOT, "demand_preprocessing", output_root=tmp_path)
    assert _payloads(tmp_path) == {
        f"{MODEL_OUTPUT_DIR}/demand_nodes.csv",
        f"{MODEL_OUTPUT_DIR}/demand_totals.csv",
        f"{MODEL_OUTPUT_DIR}/supply_nodes.csv",
        f"{MODEL_OUTPUT_DIR}/component_demand.csv",
        f"{MODEL_OUTPUT_DIR}/demand_preprocessing_audit.json",
    }


def test_network_stage_does_not_execute_demand_or_analysis(monkeypatch, tmp_path: Path):
    def fail(*args, **kwargs):
        raise AssertionError("network stage must consume demand carriers")

    monkeypatch.setattr(workflow_module, "preprocess_demand", fail)
    monkeypatch.setattr(workflow_module, "run_dynamic_analysis", fail)
    run_model_stage(ROOT, "directed_network_flow", output_root=tmp_path)
    assert _payloads(tmp_path) == {
        f"{MODEL_OUTPUT_DIR}/network_summary.csv",
        f"{MODEL_OUTPUT_DIR}/network_edge_flows.csv",
        f"{MODEL_OUTPUT_DIR}/network_service.csv",
        f"{MODEL_OUTPUT_DIR}/network_edge_catalog.csv",
        f"{MODEL_OUTPUT_DIR}/network_node_catalog.csv",
        f"{MODEL_OUTPUT_DIR}/network_model_audit.json",
    }


def test_analysis_stage_does_not_execute_upstream_models(monkeypatch, tmp_path: Path):
    def fail(*args, **kwargs):
        raise AssertionError("analysis stage must consume demand/network carriers")

    monkeypatch.setattr(workflow_module, "preprocess_demand", fail)
    monkeypatch.setattr(workflow_module, "run_network", fail)
    run_model_stage(ROOT, "dynamic_analysis", output_root=tmp_path)
    assert _payloads(tmp_path) == {
        f"{MODEL_OUTPUT_DIR}/analysis_summary.csv",
        f"{MODEL_OUTPUT_DIR}/regional_accounts.csv",
        f"{MODEL_OUTPUT_DIR}/figure_04_source.csv",
        f"{MODEL_OUTPUT_DIR}/figure_05_source.csv",
        f"{MODEL_OUTPUT_DIR}/dynamic_analysis_audit.json",
    }


@pytest.mark.parametrize(
    ("stage", "artifact"),
    [("figure_04", "figures/model-figure-04.png"), ("figure_05", "figures/model-figure-05.png")],
)
def test_figure_stage_reads_analysis_source_and_writes_only_figure(
    monkeypatch, tmp_path: Path, stage: str, artifact: str
):
    def fail(*args, **kwargs):
        raise AssertionError("figure stage must consume analysis source")

    monkeypatch.setattr(workflow_module, "run_model_chain", fail)
    run_model_stage(ROOT, stage, output_root=tmp_path)
    assert _payloads(tmp_path) == {artifact}
