import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

import green_methanol_release.safety as safety_module


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import stage_public_inputs as stage_module
from stage_public_inputs import stage_inputs
from green_methanol_release.inventory import load_dataset_registry


REGISTRY_FIELDS = (
    "dataset_id",
    "public_path",
    "role",
    "origin",
    "access_route",
    "license",
    "sha256",
    "acquisition_command",
    "processing_command",
    "manuscript_uses",
    "source_relative_path",
    "stage_action",
)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _row(
    *,
    dataset_id: str = "dataset-1",
    public_path: str = "data/staged/payload.bin",
    source_relative_path: str = "payload.bin",
    stage_action: str = "copy",
    sha256: str | None = None,
    **overrides: str,
) -> dict[str, str]:
    payload_hash = sha256 or _digest(b"public payload")
    row = {
        "dataset_id": dataset_id,
        "public_path": public_path,
        "role": "source data carrier",
        "origin": "author-generated",
        "access_route": "repository carrier",
        "license": "CC BY 4.0",
        "sha256": payload_hash,
        "acquisition_command": "",
        "processing_command": "terminal source-data carrier",
        "manuscript_uses": "Task 3 tests",
        "source_relative_path": source_relative_path,
        "stage_action": stage_action,
    }
    row.update(overrides)
    return row


def _write_registry(root: Path, rows: list[dict[str, str]]) -> Path:
    path = root / "data" / "dataset_registry.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REGISTRY_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _prepare_copy(tmp_path: Path, row: dict[str, str] | None = None) -> tuple[Path, Path, Path]:
    source_root = tmp_path / "source"
    release_root = tmp_path / "release"
    source_root.mkdir()
    source = source_root / "payload.bin"
    source.write_bytes(b"public payload")
    registry = _write_registry(tmp_path, [row or _row()])
    return registry, source_root, release_root


def test_copy_is_byte_exact_and_reports_declared_hash(tmp_path: Path):
    registry, source_root, release_root = _prepare_copy(tmp_path)

    report = stage_inputs(registry, source_root, release_root)

    destination = release_root / "data" / "staged" / "payload.bin"
    assert report["status"] == "PASS"
    assert destination.read_bytes() == b"public payload"
    assert report["totals"]["copy"] == 1
    assert report["datasets"][0]["sha256"] == _digest(b"public payload")
    assert report["datasets"][0]["bytes"] == len(b"public payload")


def test_hash_mismatch_is_reported_as_failure(tmp_path: Path):
    bad_row = _row(sha256="0" * 64)
    registry, source_root, release_root = _prepare_copy(tmp_path, bad_row)

    report = stage_inputs(registry, source_root, release_root)

    assert report["status"] == "FAIL"
    assert report["datasets"][0]["status"] == "FAIL"
    assert report["errors"][0]["code"] == "hash_mismatch"
    assert not (release_root / "data" / "staged" / "payload.bin").exists()


def test_report_is_deterministic_and_contains_no_absolute_source_root(tmp_path: Path):
    registry, source_root, release_root = _prepare_copy(tmp_path)

    first = stage_inputs(registry, source_root, release_root)
    second = stage_inputs(registry, source_root, release_root)

    assert first == second
    assert str(source_root) not in json.dumps(second, ensure_ascii=False)
    assert json.loads(json.dumps(second, ensure_ascii=False))["status"] == "PASS"


def test_report_orders_datasets_by_identifier(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    first_payload = b"first"
    second_payload = b"second"
    (source_root / "first.bin").write_bytes(first_payload)
    (source_root / "second.bin").write_bytes(second_payload)
    registry = _write_registry(
        tmp_path,
        [
            _row(
                dataset_id="dataset-b",
                public_path="data/staged/second.bin",
                source_relative_path="second.bin",
                sha256=_digest(second_payload),
            ),
            _row(
                dataset_id="dataset-a",
                public_path="data/staged/first.bin",
                source_relative_path="first.bin",
                sha256=_digest(first_payload),
            ),
        ],
    )

    report = stage_inputs(registry, source_root, tmp_path / "release")

    assert report["status"] == "PASS"
    assert [row["dataset_id"] for row in report["datasets"]] == ["dataset-a", "dataset-b"]


def test_missing_source_is_reported_without_absolute_path(tmp_path: Path):
    row = _row(source_relative_path="missing.bin")
    registry = _write_registry(tmp_path, [row])

    report = stage_inputs(registry, tmp_path / "source", tmp_path / "release")

    assert report["status"] == "FAIL"
    assert report["errors"][0]["code"] == "missing_source"
    assert str(tmp_path) not in json.dumps(report, ensure_ascii=False)


def test_malformed_action_is_rejected_before_source_access(tmp_path: Path):
    row = _row(stage_action="move", source_relative_path="does-not-exist.bin")
    registry = _write_registry(tmp_path, [row])

    report = stage_inputs(registry, tmp_path / "source", tmp_path / "release")

    assert report["status"] == "FAIL"
    assert report["errors"][0]["code"] == "malformed_action"


def test_copy_requires_declared_source(tmp_path: Path):
    row = _row(source_relative_path="")
    registry = _write_registry(tmp_path, [row])

    report = stage_inputs(registry, tmp_path / "source", tmp_path / "release")

    assert report["status"] == "FAIL"
    assert report["errors"][0]["code"] == "undeclared_source"


def test_forbidden_source_is_rejected_without_inspecting_excluded_directory(tmp_path: Path):
    row = _row(source_relative_path="safe/管道数据/payload.bin")
    registry = _write_registry(tmp_path, [row])

    report = stage_inputs(registry, tmp_path / "source", tmp_path / "release")

    assert report["status"] == "FAIL"
    assert report["errors"][0]["code"] == "forbidden_source"


def test_symlink_source_alias_to_excluded_component_is_rejected_before_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(stage_module, "_FORBIDDEN_COMPONENT", "blocked-component")
    monkeypatch.setattr(safety_module, "_FORBIDDEN_COMPONENT", "blocked-component")
    source_root = tmp_path / "source"
    source_root.mkdir()
    blocked = source_root / "blocked-component"
    blocked.mkdir()
    payload = blocked / "payload.bin"
    payload.write_bytes(b"public payload")
    alias = source_root / "alias.bin"
    try:
        alias.symlink_to(payload)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    row = _row(source_relative_path="alias.bin")
    registry = _write_registry(tmp_path, [row])

    report = stage_inputs(registry, source_root, tmp_path / "release")

    assert report["status"] == "FAIL"
    assert report["errors"][0]["code"] == "forbidden_source"
    assert not (tmp_path / "release" / "data" / "staged" / "payload.bin").exists()


def test_early_registry_error_totals_match_empty_dataset_report(tmp_path: Path):
    row = _row(source_relative_path="safe/管道数据/payload.bin")
    registry = _write_registry(tmp_path, [row])

    report = stage_inputs(registry, tmp_path / "source", tmp_path / "release")

    assert report["status"] == "FAIL"
    assert report["datasets"] == []
    assert report["totals"]["datasets"] == 0
    assert report["totals"]["failed"] == 0
    assert report["totals"]["errors"] == len(report["errors"]) == 1


def test_forbidden_destination_is_rejected_before_copy(tmp_path: Path):
    row = _row(public_path="data/管道数据/payload.bin")
    registry, source_root, release_root = _prepare_copy(tmp_path, row)

    report = stage_inputs(registry, source_root, release_root)

    assert report["status"] == "FAIL"
    assert report["errors"][0]["code"] == "forbidden_destination"
    assert not (release_root / "data" / "管道数据").exists()


def test_acquire_does_not_open_source_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source_root = tmp_path / "source"
    source_root.mkdir()
    sentinel = source_root / "unopened.bin"
    sentinel.write_bytes(b"must not be read")
    row = _row(
        public_path="data/external/gs2023_2767_acquisition.json",
        source_relative_path="",
        stage_action="acquire",
        role="third-party catalogue metadata",
        origin="third-party official catalogue",
        access_route="official catalogue",
        license="not relicensed",
        acquisition_command="download official GS(2023)2767 catalogue after rights review",
        processing_command="metadata-only acquisition record",
    )
    registry = _write_registry(tmp_path, [row])

    original_open = Path.open

    def guarded_open(path: Path, *args, **kwargs):
        if path == sentinel:
            raise AssertionError("acquire action opened its source payload")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    report = stage_inputs(registry, source_root, tmp_path / "release")

    assert report["status"] == "PASS"
    assert report["datasets"][0]["status"] == "PASS"
    assert report["datasets"][0]["stage_action"] == "acquire"
    assert report["datasets"][0]["bytes"] is None


def test_existing_hash_is_validated(tmp_path: Path):
    release_root = tmp_path / "release"
    destination = release_root / "data" / "staged" / "payload.bin"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"public payload")
    row = _row(
        public_path="data/staged/payload.bin",
        source_relative_path="",
        stage_action="existing",
    )
    registry = _write_registry(tmp_path, [row])

    report = stage_inputs(registry, tmp_path / "source", release_root)

    assert report["status"] == "PASS"
    assert report["datasets"][0]["bytes"] == len(b"public payload")

    destination.write_bytes(b"changed")
    failed = stage_inputs(registry, tmp_path / "source", release_root)

    assert failed["status"] == "FAIL"
    assert failed["errors"][0]["code"] == "hash_mismatch"


def test_cli_writes_utf8_lf_json(tmp_path: Path):
    registry, source_root, release_root = _prepare_copy(tmp_path)
    report_path = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "stage_public_inputs.py"),
            "--registry",
            str(registry),
            "--source-root",
            str(source_root),
            "--release-root",
            str(release_root),
            "--report",
            str(report_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    raw = report_path.read_bytes()
    assert b"\r" not in raw
    assert json.loads(raw.decode("utf-8"))["status"] == "PASS"


def test_cli_rejects_forbidden_report_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list[tuple[object, ...]] = []

    def forbidden_stage(*args: object, **kwargs: object) -> dict[str, object]:
        calls.append(args)
        raise AssertionError("stage_inputs must not run for an unsafe report path")

    monkeypatch.setattr(stage_module, "stage_inputs", forbidden_stage)
    report_path = tmp_path / "reports" / "管道数据" / "report.json"

    result = stage_module.main(
        [
            "--registry",
            str(tmp_path / "registry.csv"),
            "--source-root",
            str(tmp_path / "source"),
            "--release-root",
            str(tmp_path / "release"),
            "--report",
            str(report_path),
        ]
    )

    assert result == 2
    assert calls == []
    assert not report_path.exists()


def test_cli_rejects_directory_report_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list[tuple[object, ...]] = []

    def forbidden_stage(*args: object, **kwargs: object) -> dict[str, object]:
        calls.append(args)
        raise AssertionError("stage_inputs must not run for an invalid report path")

    monkeypatch.setattr(stage_module, "stage_inputs", forbidden_stage)

    result = stage_module.main(
        [
            "--registry",
            str(tmp_path / "registry.csv"),
            "--source-root",
            str(tmp_path / "source"),
            "--release-root",
            str(tmp_path / "release"),
            "--report",
            str(tmp_path),
        ]
    )

    assert result == 2
    assert calls == []


def test_extended_registry_loader_returns_stage_columns(tmp_path: Path):
    row = _row()
    registry = _write_registry(tmp_path, [row])

    loaded = load_dataset_registry(registry)

    assert loaded == [row]


REAL_COPY_MAPPINGS = {
    "data/figure_source/figure-02.csv":
        "727修改/.worktrees/city-topology-v01/outputs/manuscript_v117_figures/figure-02_source_data.csv",
    "data/processed/dynamic_analyses_v08/c1_logistics.csv":
        "727修改/data/derived/dynamic_analyses_v08/c1_logistics.csv",
    "data/figure_source/figure-04.csv":
        "727修改/.worktrees/city-topology-v01/outputs/manuscript_v115_figures/figure-04_source_data.csv",
    "data/figure_source/figure-05.csv":
        "727修改/.worktrees/city-topology-v01/outputs/manuscript_v115_figures/figure-05_source_data.csv",
    "data/raw/pipeline/pipeline_network_segments_v01.csv":
        "727修改/data/baseline/pipeline_network_segments_v01.csv",
    "data/raw/pipeline/segment_transport_task_pipeline_adjusted_long.csv":
        "_codex_pipeline_transport_correction_work/segment_transport_task_pipeline_adjusted_long.csv",
    "data/raw/pipeline/pipeline_level_utilization_long.csv":
        "_codex_pipeline_level_utilization_work/pipeline_level_utilization_long.csv",
    "data/raw/pipeline/pipeline_nodes_geocoded.csv":
        "_codex_node_clustering_work/pipeline_nodes_geocoded.csv",
    "data/raw/pipeline/city_assignments.csv":
        "_codex_node_clustering_work/city_assignments.csv",
    "data/raw/pipeline/pipeline_edges_with_node_coords.csv":
        "_codex_node_clustering_work/pipeline_edges_with_node_coords.csv",
    "data/raw/supply/province_projection_nbs_generation.csv":
        "_codex_methanol_supply_work/data/province_projection_nbs_generation.csv",
    "data/raw/demand/province_demand_corrected_product_coeff.csv":
        "_codex_sinopec_demand_work/province_demand_corrected_product_coeff.csv",
    "data/raw/demand/province_origin_2024.csv":
        "tmp/aviation_methanol/processed/province_origin_2024.csv",
    "data/raw/official_sources/mot_2025_shipping_port_weights.csv":
        "data/official_sources/mot_2025_port_throughput/mot_2025_shipping_port_weights.csv",
}

REAL_CITY_TOPOLOGY_FILES = (
    "city_master_2024.csv",
    "city_aliases_v01.csv",
    "station_city_overrides_v01.csv",
    "trucking_city_activity.csv",
    "shipping_city_activity.csv",
    "chemical_city_activity.csv",
    "aviation_refinery_city_activity.csv",
    "city_proxy_supply_weights.csv",
    "green_methanol_projects_city.csv",
    "source_manifest.csv",
)

REAL_TOPOLOGY_FILES = (
    "candidate_links.csv",
    "topology_node_audit.csv",
    "edge_flows.csv",
    "best_two_link_plans.csv",
    "capacity_sensitivity_5point.csv",
)


def _real_registry_rows() -> list[dict[str, str]]:
    return load_dataset_registry(ROOT / "data" / "dataset_registry.csv")


def _repo_relative(path: str) -> Path:
    return ROOT / Path(*path.split("/"))


def test_real_registry_declares_every_explicit_copy_and_map_record():
    rows = {row["public_path"]: row for row in _real_registry_rows()}
    expected = dict(REAL_COPY_MAPPINGS)
    expected.update(
        {
            f"data/raw/city_topology_v01/{name}":
                f"727修改/.worktrees/city-topology-v01/data/baseline/city_topology_v01/{name}"
            for name in REAL_CITY_TOPOLOGY_FILES
        }
    )
    expected.update(
        {
            f"data/raw/topology/{name}":
                f"727修改/.worktrees/city-topology-v01/data/baseline/submission_data_v038/topology/{name}"
            for name in REAL_TOPOLOGY_FILES
        }
    )
    expected.update(
        {
            "data/raw/topology/regional_connector_gain.csv":
                "727修改/.worktrees/city-topology-v01/data/baseline/topology_increment/regional_connector_gain.csv",
            "data/processed/dynamic_analyses_v08/c3_unlocking_cost.csv":
                "727修改/.worktrees/city-topology-v01/data/derived/c3_unlocking_cost.csv",
            "data/processed/dynamic_analyses_v08/regional_accounts.csv":
                "727修改/.worktrees/city-topology-v01/data/derived/dynamic_analyses_v08/regional_accounts.csv",
            "data/processed/dynamic_analyses_v08/aviation_nodes.csv":
                "727修改/.worktrees/city-topology-v01/data/derived/dynamic_analyses_v08/aviation_nodes.csv",
        }
    )

    assert {
        public_path: rows[public_path]["source_relative_path"]
        for public_path in expected
        if public_path in rows
    } == {
        public_path: source_path for public_path, source_path in expected.items()
    }
    assert all(rows[public_path]["stage_action"] == "copy" for public_path in expected)

    map_row = rows["data/external/maps/standard_map_gs2023_2767.json"]
    assert map_row["stage_action"] == "acquire"
    assert map_row["source_relative_path"] == ""
    assert map_row["acquisition_command"] == (
        "catalogue metadata: "
        "http://bzdt.ch.mnr.gov.cn/download.html?searchText=GS(2023)2767"
    )
    assert map_row["license"] == "third-party/not-relicensed"
    metadata = _repo_relative("data/external/maps/standard_map_gs2023_2767.json")
    assert metadata.is_file()
    assert json.loads(metadata.read_text(encoding="utf-8"))["source_url"] == (
        "http://bzdt.ch.mnr.gov.cn/download.html?searchText=GS(2023)2767"
    )


def test_real_copy_and_existing_hashes_match_deposited_bytes():
    rows = _real_registry_rows()

    for row in rows:
        if row["stage_action"] not in {"copy", "existing"}:
            continue
        deposited = _repo_relative(row["public_path"])
        assert deposited.is_file(), row["public_path"]
        assert _digest(deposited.read_bytes()) == row["sha256"]


def test_real_figure_02_has_required_row_count_and_record_types():
    source = _repo_relative("data/figure_source/figure-02.csv")
    with source.open(encoding="utf-8", newline="") as handle:
        records = list(csv.DictReader(handle))

    assert len(records) == 494
    record_type_counts = Counter(record["case"] for record in records)
    assert {
        record_type: record_type_counts[record_type]
        for record_type in (
            "complete_existing_network",
            "existing_network_design_throughput",
            "model_called_task",
            "province_demand_coverage",
        )
    } == {
        "complete_existing_network": 140,
        "existing_network_design_throughput": 140,
        "model_called_task": 11,
        "province_demand_coverage": 29,
    }


def test_real_staging_report_passes_and_counts_all_actions():
    report_path = ROOT / "qa" / "staging_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["status"] == "PASS"
    assert report["totals"] == {
        "datasets": 39,
        "copy": 33,
        "existing": 5,
        "acquire": 1,
        "passed": 39,
        "failed": 0,
        "errors": 0,
    }
    assert str(ROOT.parents[2]) not in json.dumps(report, ensure_ascii=False)


def test_real_tracked_and_staged_paths_exclude_forbidden_component():
    forbidden = stage_module._FORBIDDEN_COMPONENT.encode("utf-8")
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")

    def has_forbidden_component(paths: list[bytes]) -> bool:
        return any(forbidden in path.replace(b"\\", b"/").split(b"/") for path in paths if path)

    assert not has_forbidden_component(tracked)
    assert not has_forbidden_component(staged)
