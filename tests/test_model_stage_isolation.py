from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from green_methanol_release.inventory import load_dataset_registry, load_output_registry
from green_methanol_release.model.analysis import (
    ANALYSIS_FIGURE_SOURCES,
    ANALYSIS_INPUTS,
    ANALYSIS_OUTPUTS,
)
from green_methanol_release.model.demand import DEMAND_INPUTS, DEMAND_OUTPUTS
from green_methanol_release.model.network import (
    NETWORK_INPUTS,
    NETWORK_OUTPUTS,
    NETWORK_STAGE_INPUTS,
)
from green_methanol_release.model import workflow as workflow_module
from green_methanol_release.model.workflow import MODEL_OUTPUT_DIR, run_model_stage


ROOT = Path(__file__).resolve().parents[1]


def _copy_release(tmp_path: Path, name: str = "release") -> Path:
    root = tmp_path / name
    shutil.copytree(
        ROOT,
        root,
        ignore=shutil.ignore_patterns(".venv", ".git", "__pycache__", ".pytest_cache"),
    )
    return root


def _payloads(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


def _rewrite_audit_with_self_hash(path: Path, payload: dict[str, object]) -> None:
    payload = dict(payload)
    payload.pop("audit_sha256", None)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    payload["audit_sha256"] = hashlib.sha256(canonical).hexdigest()
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


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


def test_network_stage_rejects_mutated_persisted_demand_artifact(tmp_path: Path):
    root = _copy_release(tmp_path, "mutated_demand")
    demand_path = root / "data" / "processed" / "model_v01" / "demand_nodes.csv"
    network_path = root / "data" / "processed" / "model_v01" / "network_summary.csv"
    before = network_path.read_bytes()
    demand_path.write_bytes(demand_path.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="hash|persisted"):
        run_model_stage(root, "directed_network_flow", output_root=root)

    assert network_path.read_bytes() == before


def test_stage_rejects_undeclared_input_path_before_execution():
    with pytest.raises(ValueError, match="input"):
        run_model_stage(
            ROOT,
            "demand_preprocessing",
            input_paths=["data/raw/demand/not-declared.csv"],
        )


@pytest.mark.parametrize(
    ("script_name", "input_paths"),
    [
        ("preprocess_demand", tuple(DEMAND_INPUTS.values())),
        ("run_network", tuple(NETWORK_STAGE_INPUTS.values())),
        ("build_analysis", tuple(ANALYSIS_INPUTS.values())),
        ("build_figure_04", (ANALYSIS_FIGURE_SOURCES["figure_04"],)),
        ("build_figure_05", (ANALYSIS_FIGURE_SOURCES["figure_05"],)),
    ],
)
def test_model_cli_rejects_wrong_output_before_running_stage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    script_name: str,
    input_paths: tuple[str, ...],
):
    script_path = ROOT / "scripts" / "model" / f"{script_name}.py"
    spec = importlib.util.spec_from_file_location(
        f"model_cli_{script_name}", script_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls: list[tuple[object, ...]] = []

    def forbidden_run(*args: object, **kwargs: object):
        calls.append(args)
        raise AssertionError("wrong --output must be rejected before stage execution")

    monkeypatch.setattr(module, "run_model_stage", forbidden_run)
    wrong_output = tmp_path / "wrong-output.bin"
    argv: list[str] = []
    for input_path in input_paths:
        argv.extend(("--input", input_path))
    argv.extend(("--output", str(wrong_output)))

    assert module.main(argv) == 1
    assert calls == []
    assert not wrong_output.exists()


def test_network_loader_rejects_mutated_artifact_against_persisted_audit(tmp_path: Path):
    root = _copy_release(tmp_path, "mutated_network")
    artifact = root / "data" / "processed" / "model_v01" / "network_edge_flows.csv"
    artifact.write_bytes(artifact.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="hash|artifact"):
        workflow_module.load_network_outputs(root)


def test_demand_loader_rejects_rewritten_input_hash_against_registry(tmp_path: Path):
    root = _copy_release(tmp_path, "mutated_demand_input")
    relative = DEMAND_INPUTS["city_master"]
    path = root / Path(*relative.split("/"))
    path.write_bytes(path.read_bytes() + b"\n")
    audit_path = root / Path(*DEMAND_OUTPUTS["audit"].split("/"))
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    payload["input_hashes"][relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    _rewrite_audit_with_self_hash(audit_path, payload)

    with pytest.raises(ValueError, match="registry|input hash"):
        workflow_module.load_demand_outputs(root)


def test_network_loader_rejects_rewritten_raw_input_hash_against_registry(
    tmp_path: Path,
):
    root = _copy_release(tmp_path, "mutated_network_input")
    relative = NETWORK_INPUTS["pipeline_nodes"]
    path = root / Path(*relative.split("/"))
    path.write_bytes(path.read_bytes() + b"\n")
    audit_path = root / Path(*NETWORK_OUTPUTS["audit"].split("/"))
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    payload["input_hashes"][f"network::{relative}"] = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()
    _rewrite_audit_with_self_hash(audit_path, payload)

    with pytest.raises(ValueError, match="registry|input hash"):
        workflow_module.load_network_outputs(root)


def test_analysis_loader_rejects_rewritten_candidate_hash_against_registry(
    tmp_path: Path,
):
    root = _copy_release(tmp_path, "mutated_analysis_input")
    relative = ANALYSIS_INPUTS["candidate_links"]
    path = root / Path(*relative.split("/"))
    path.write_bytes(path.read_bytes() + b"\n")
    audit_path = root / Path(*ANALYSIS_OUTPUTS["audit"].split("/"))
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    current_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    payload["input_hashes"][relative] = current_hash
    payload["counterfactuals"]["candidate_input_hashes"][relative] = current_hash
    _rewrite_audit_with_self_hash(audit_path, payload)

    with pytest.raises(ValueError, match="registry|input hash"):
        workflow_module.load_analysis_outputs(root)


def test_network_loader_rejects_rewritten_upstream_demand_hash_chain(
    tmp_path: Path,
):
    root = _copy_release(tmp_path, "mutated_upstream_demand")
    relative = DEMAND_OUTPUTS["nodes"]
    path = root / Path(*relative.split("/"))
    path.write_bytes(path.read_bytes() + b"\n")
    audit_path = root / Path(*NETWORK_OUTPUTS["audit"].split("/"))
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    payload["input_hashes"][f"demand::{relative}"] = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()
    _rewrite_audit_with_self_hash(audit_path, payload)

    with pytest.raises(ValueError, match="hash|persisted"):
        workflow_module.load_network_outputs(root)


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
