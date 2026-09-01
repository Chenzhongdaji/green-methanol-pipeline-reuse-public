from __future__ import annotations

import csv
import hashlib
from pathlib import Path
import random
import shutil

import networkx as nx
import pandas as pd
import pytest

from green_methanol_release.model.network import (
    validate_flow_conservation,
)
from green_methanol_release.model.workflow import run_model_chain


ROOT = Path(__file__).resolve().parents[1]


def _frame_hash(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _model_input_root(tmp_path: Path) -> Path:
    root = tmp_path / "release"
    for relative in (
        "config",
        "data/raw/demand",
        "data/raw/supply",
        "data/raw/official_sources",
        "data/raw/city_topology_v01",
        "data/raw/pipeline",
        "data/raw/topology",
    ):
        shutil.copytree(ROOT / Path(*relative.split("/")), root / Path(*relative.split("/")))
    return root


def test_flow_conservation_rejects_perturbed_internal_node():
    graph = nx.DiGraph()
    graph.add_edges_from(
        [
            ("__source__", "A"),
            ("A", "__sink__"),
        ]
    )
    flow = {
        "__source__": {"A": 10},
        "A": {"__sink__": 9},
        "__sink__": {},
    }

    with pytest.raises(ValueError, match="flow conservation"):
        validate_flow_conservation(graph, flow)


def test_real_network_records_case_node_and_source_sink_conservation():
    result = run_model_chain(ROOT, write_outputs=False)

    evidence = result.network.audit["flow_conservation"]
    assert evidence["status"] == "PASS"
    assert evidence["cases"] == len(result.network.summary)
    assert evidence["max_internal_residual_units"] == 0
    assert evidence["max_source_sink_residual_units"] == 0


def test_core_outputs_are_invariant_to_input_row_permutation(tmp_path: Path):
    root = _model_input_root(tmp_path)
    first = run_model_chain(root, write_outputs=False)
    for relative in (
        "data/raw/pipeline/pipeline_network_segments_v01.csv",
        "data/raw/pipeline/segment_transport_task_pipeline_adjusted_long.csv",
        "data/raw/demand/province_demand_corrected_product_coeff.csv",
        "data/raw/demand/province_origin_2024.csv",
        "data/raw/supply/province_projection_nbs_generation.csv",
    ):
        path = root / Path(*relative.split("/"))
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        header, body = rows[0], rows[1:]
        random.Random(20260901).shuffle(body)
        with path.open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle, lineterminator="\n").writerows([header, *body])
    second = run_model_chain(root, write_outputs=False)

    for left, right in (
        (first.demand.nodes, second.demand.nodes),
        (first.demand.totals, second.demand.totals),
        (first.demand.supply, second.demand.supply),
        (first.network.summary, second.network.summary),
        (first.network.edge_flows, second.network.edge_flows),
        (first.analysis.regional_accounts, second.analysis.regional_accounts),
        (first.analysis.figure_04_source, second.analysis.figure_04_source),
        (first.analysis.figure_05_source, second.analysis.figure_05_source),
    ):
        assert _frame_hash(left) == _frame_hash(right)
        assert len(left) == len(right)
