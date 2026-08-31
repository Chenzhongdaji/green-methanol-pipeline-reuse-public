import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _run_builder(script: str, input_path: str, output_path: Path, *extra: str):
    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"
    return subprocess.run(
        [
            sys.executable,
            f"scripts/{script}",
            "--input",
            input_path,
            "--output",
            str(output_path),
            *extra,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_figure_02_panel_e_uses_exact_public_row_contract_and_writes_sibling_pdf(tmp_path):
    output = tmp_path / "figure-02e.png"

    completed = _run_builder(
        "build_figure_02.py",
        "data/figure_source/figure-02.csv",
        output,
        "--panel",
        "e",
    )

    assert completed.returncode == 0, completed.stderr
    metadata = json.loads(completed.stdout)
    assert metadata["input_row_count"] == 494
    assert metadata["plotted_record_counts"] == {
        "complete_existing_network": 140,
        "existing_network_design_throughput": 140,
        "model_called_task": 11,
        "province_demand_coverage": 29,
    }
    assert metadata["output_path"] == str(output)
    assert metadata["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert metadata["plotted_records"] == 320
    assert output.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert output.stat().st_size > 1_000
    assert output.with_suffix(".pdf").is_file()
    assert output.with_suffix(".pdf").stat().st_size > 1_000


def test_figure_02_panel_e_reports_sorted_coverage_label_value_pairs(tmp_path):
    output = tmp_path / "figure-02e.png"

    completed = _run_builder(
        "build_figure_02.py",
        "data/figure_source/figure-02.csv",
        output,
        "--panel",
        "e",
    )

    assert completed.returncode == 0, completed.stderr
    metadata = json.loads(completed.stdout)
    coverage = metadata["coverage_summary"]
    assert [item["label"] for item in coverage] == sorted(item["label"] for item in coverage)
    assert coverage[0] == {"label": "上海", "value": 0.0}
    assert coverage[1] == {"label": "云南", "value": 87.7668176392895}


def test_figure_02_panel_e_png_hash_is_deterministic(tmp_path):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"

    one = _run_builder(
        "build_figure_02.py",
        "data/figure_source/figure-02.csv",
        first,
        "--panel",
        "e",
    )
    two = _run_builder(
        "build_figure_02.py",
        "data/figure_source/figure-02.csv",
        second,
        "--panel",
        "e",
    )

    assert one.returncode == 0, one.stderr
    assert two.returncode == 0, two.stderr
    assert hashlib.sha256(first.read_bytes()).hexdigest() == hashlib.sha256(second.read_bytes()).hexdigest()


def test_figure_02_panel_e_rejects_nonfinite_coordinates(tmp_path):
    source = ROOT / "data" / "figure_source" / "figure-02.csv"
    malformed = tmp_path / "nonfinite.csv"
    with source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    network = next(
        row for row in rows if row["panel"] == "e" and row["case"] == "complete_existing_network"
    )
    network["x"] = "nan,100"
    with malformed.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    completed = _run_builder("build_figure_02.py", str(malformed), tmp_path / "nonfinite.png", "--panel", "e")

    assert completed.returncode != 0
    assert "non-finite" in completed.stderr.lower()


def test_figure_02_panel_e_requires_model_tasks_to_be_existing_edges(tmp_path):
    source = ROOT / "data" / "figure_source" / "figure-02.csv"
    malformed = tmp_path / "orphan-task.csv"
    with source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    task = next(row for row in rows if row["panel"] == "e" and row["case"] == "model_called_task")
    task["note"] = "N999->N998; assigned task only"
    with malformed.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    completed = _run_builder("build_figure_02.py", str(malformed), tmp_path / "orphan-task.png", "--panel", "e")

    assert completed.returncode != 0
    assert "task edge" in completed.stderr.lower()


def test_figure_02_panel_e_rejects_network_note_carrier_throughput_mismatch(tmp_path):
    source = ROOT / "data" / "figure_source" / "figure-02.csv"
    malformed = tmp_path / "throughput-mismatch.csv"
    with source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    network = next(
        row for row in rows if row["panel"] == "e" and row["case"] == "complete_existing_network"
    )
    network["note"] = network["note"].replace("design throughput=1000", "design throughput=999", 1)
    with malformed.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    completed = _run_builder(
        "build_figure_02.py", str(malformed), tmp_path / "throughput-mismatch.png", "--panel", "e"
    )

    assert completed.returncode != 0
    assert "throughput" in completed.stderr.lower()


def test_figure_02_panel_e_is_deterministic_under_carrier_row_permutation(tmp_path):
    source = ROOT / "data" / "figure_source" / "figure-02.csv"
    permuted = tmp_path / "permuted.csv"
    with source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    with permuted.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(list(reversed(rows)))

    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    one = _run_builder("build_figure_02.py", "data/figure_source/figure-02.csv", first, "--panel", "e")
    two = _run_builder("build_figure_02.py", str(permuted), second, "--panel", "e")

    assert one.returncode == 0, one.stderr
    assert two.returncode == 0, two.stderr
    assert hashlib.sha256(first.read_bytes()).hexdigest() == hashlib.sha256(second.read_bytes()).hexdigest()


def test_figure_02_rejects_empty_input(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text(
        "panel,scenario,year,case,metric,value,unit,denominator,source_type,style,x,y,note\n",
        encoding="utf-8",
        newline="\n",
    )
    output = tmp_path / "empty.png"

    completed = _run_builder("build_figure_02.py", str(empty), output, "--panel", "e")

    assert completed.returncode != 0
    assert "empty" in completed.stderr.lower()
    assert not output.exists()


def test_figure_02_summary_rejects_panel_with_no_rendered_records(tmp_path):
    source = ROOT / "data" / "figure_source" / "figure-02.csv"
    malformed = tmp_path / "empty-render.csv"
    with source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    for row in rows:
        if row["panel"] == "a":
            row["style"] = "trajectory"
            row["value"] = ""
            row["y"] = ""
            row["note"] = "N.A. test row"
    with malformed.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    completed = _run_builder(
        "build_figure_02.py", str(malformed), tmp_path / "empty-render.png", "--panels", "a-d,f-h"
    )

    assert completed.returncode != 0
    assert "rendered" in completed.stderr.lower()


def test_figure_02_supports_both_panel_modes(tmp_path):
    panel_e = tmp_path / "panel-e.png"
    panels = tmp_path / "panels.png"

    one = _run_builder(
        "build_figure_02.py",
        "data/figure_source/figure-02.csv",
        panel_e,
        "--panel",
        "e",
    )
    many = _run_builder(
        "build_figure_02.py",
        "data/figure_source/figure-02.csv",
        panels,
        "--panels",
        "a-d,f-h",
    )

    assert one.returncode == 0, one.stderr
    assert many.returncode == 0, many.stderr
    assert panel_e.is_file() and panels.is_file()
    assert panel_e.read_bytes() != panels.read_bytes()


def test_figure_02_rejects_malformed_coordinates(tmp_path):
    source = ROOT / "data" / "figure_source" / "figure-02.csv"
    malformed = tmp_path / "malformed.csv"
    with source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    malformed_row = next(
        row for row in rows if row["panel"] == "e" and row["case"] == "complete_existing_network"
    )
    malformed_row["x"] = "not-a-coordinate"
    with malformed.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    output = tmp_path / "malformed.png"

    completed = _run_builder("build_figure_02.py", str(malformed), output, "--panel", "e")

    assert completed.returncode != 0
    assert "coordinate" in completed.stderr.lower()
    assert not output.exists()


def test_all_registry_builders_exist_and_figure_02_uses_real_carrier():
    registry = ROOT / "data" / "output_registry.csv"
    with registry.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    figure2_rows = [row for row in rows if row["output_id"].startswith("figure-02")]
    assert [row["output_id"] for row in figure2_rows] == ["figure-02a-d-f-h", "figure-02e"]
    for row in figure2_rows:
        tokens = row["generation_command"].split()
        script_token = next(token for token in tokens if token.startswith("scripts/build_figure_"))
        assert (ROOT / script_token).is_file()
        assert "data/figure_source/figure-02.csv" in row["generation_command"]
        assert row["input_dataset_ids"] == "figure-02-source-real"


@pytest.mark.parametrize(
    ("script", "source", "output_name", "expected_rows"),
    [
        ("build_figure_01.py", "figure-01.csv", "figure-01.png", 35),
        ("build_figure_03.py", "figure-03.csv", "figure-03.png", 8),
        ("build_figure_04.py", "figure-04.csv", "figure-04.png", 56),
        ("build_figure_05.py", "figure-05.csv", "figure-05.png", 16),
    ],
)
def test_remaining_builders_accept_exact_public_schema_and_emit_metadata(
    tmp_path, script, source, output_name, expected_rows
):
    output = tmp_path / output_name

    completed = _run_builder(script, f"figures/source_data/{source}", output)

    assert completed.returncode == 0, completed.stderr
    metadata = json.loads(completed.stdout)
    assert metadata["input_row_count"] == expected_rows
    assert metadata["output_path"] == str(output)
    assert metadata["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert metadata["plotted_records"] > 0
    assert output.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert output.stat().st_size > 1_000


@pytest.mark.parametrize(
    ("script", "source"),
    [
        ("build_figure_01.py", "figure-01.csv"),
        ("build_figure_03.py", "figure-03.csv"),
        ("build_figure_04.py", "figure-04.csv"),
        ("build_figure_05.py", "figure-05.csv"),
    ],
)
def test_remaining_builders_have_deterministic_hashes_under_row_permutation(
    tmp_path, script, source
):
    original = ROOT / "figures" / "source_data" / source
    permuted = tmp_path / source
    with original.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    with permuted.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(reversed(rows))

    first = tmp_path / f"first-{source[:-4]}.png"
    second = tmp_path / f"second-{source[:-4]}.png"
    one = _run_builder(script, f"figures/source_data/{source}", first)
    two = _run_builder(script, str(permuted), second)

    assert one.returncode == 0, one.stderr
    assert two.returncode == 0, two.stderr
    assert hashlib.sha256(first.read_bytes()).hexdigest() == hashlib.sha256(
        second.read_bytes()
    ).hexdigest()


@pytest.mark.parametrize(
    ("script", "source"),
    [
        ("build_figure_01.py", "figure-01.csv"),
        ("build_figure_03.py", "figure-03.csv"),
        ("build_figure_04.py", "figure-04.csv"),
        ("build_figure_05.py", "figure-05.csv"),
    ],
)
def test_remaining_builders_reject_empty_input(tmp_path, script, source):
    source_path = ROOT / "figures" / "source_data" / source
    header = source_path.read_text(encoding="utf-8-sig").splitlines()[0]
    empty = tmp_path / f"empty-{source}"
    empty.write_text(header + "\n", encoding="utf-8", newline="\n")
    output = tmp_path / f"empty-{source[:-4]}.png"

    completed = _run_builder(script, str(empty), output)

    assert completed.returncode != 0
    assert "empty" in completed.stderr.lower()
    assert not output.exists()


@pytest.mark.parametrize(
    ("script", "source", "field"),
    [
        ("build_figure_03.py", "figure-03.csv", "distance_km"),
        ("build_figure_04.py", "figure-04.csv", "served_methanol_10kt"),
        ("build_figure_05.py", "figure-05.csv", "value"),
    ],
)
def test_remaining_builders_reject_nonfinite_numeric_fields(
    tmp_path, script, source, field
):
    source_path = ROOT / "figures" / "source_data" / source
    with source_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    rows[0][field] = "nan"
    malformed = tmp_path / f"nonfinite-{source}"
    with malformed.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    output = tmp_path / f"nonfinite-{source[:-4]}.png"
    completed = _run_builder(script, str(malformed), output)

    assert completed.returncode != 0
    assert "non-finite" in completed.stderr.lower()
    assert not output.exists()


def test_figure_01_rejects_unknown_target(tmp_path):
    source_path = ROOT / "figures" / "source_data" / "figure-01.csv"
    with source_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    rows[0]["target"] = "not-a-conceptual-stage"
    malformed = tmp_path / "unknown-target.csv"
    with malformed.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    completed = _run_builder("build_figure_01.py", str(malformed), tmp_path / "unknown-target.png")

    assert completed.returncode != 0
    assert "target" in completed.stderr.lower()


def test_figure_05_rejects_value_that_disagrees_with_explicit_gain_column(tmp_path):
    source_path = ROOT / "figures" / "source_data" / "figure-05.csv"
    with source_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    rows[0]["value"] = "999"
    malformed = tmp_path / "gain-mismatch.csv"
    with malformed.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    completed = _run_builder("build_figure_05.py", str(malformed), tmp_path / "gain-mismatch.png")

    assert completed.returncode != 0
    assert "gain" in completed.stderr.lower()


@pytest.mark.parametrize(("field", "value"), [("tier", "high"), ("year", "2061")])
def test_figure_04_rejects_mixed_tier_or_year_carrier(tmp_path, field, value):
    source_path = ROOT / "figures" / "source_data" / "figure-04.csv"
    with source_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    rows[0][field] = value
    malformed = tmp_path / f"mixed-{field}.csv"
    with malformed.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    completed = _run_builder("build_figure_04.py", str(malformed), tmp_path / f"mixed-{field}.png")

    assert completed.returncode != 0
    assert "tier/year" in completed.stderr.lower()


def test_figure_04_extreme_float_region_totals_are_hash_stable_under_row_permutation(tmp_path):
    source_path = ROOT / "figures" / "source_data" / "figure-04.csv"
    with source_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    for row in rows:
        if row["region"] == "EC":
            row["demand_methanol_10kt"] = "10000000000000000" if row["scenario"] == "S1" else "1"
            row["local_direct_methanol_10kt"] = "0"
            row["pipeline_served_methanol_10kt"] = "0"
            row["served_methanol_10kt"] = "0"
            row["unserved_methanol_10kt"] = row["demand_methanol_10kt"]
            row["demand_met_pct"] = "0"
            row["pipeline_share_pct"] = "0"
    ordered = tmp_path / "extreme-ordered.csv"
    permuted = tmp_path / "extreme-permuted.csv"
    for path, payload in ((ordered, rows), (permuted, list(reversed(rows)))):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(payload)

    first = tmp_path / "extreme-first.png"
    second = tmp_path / "extreme-second.png"
    one = _run_builder("build_figure_04.py", str(ordered), first)
    two = _run_builder("build_figure_04.py", str(permuted), second)

    assert one.returncode == 0, one.stderr
    assert two.returncode == 0, two.stderr
    one_metadata = json.loads(one.stdout)
    two_metadata = json.loads(two.stdout)
    assert one_metadata["regional_totals"] == two_metadata["regional_totals"]
    assert hashlib.sha256(first.read_bytes()).hexdigest() == hashlib.sha256(
        second.read_bytes()
    ).hexdigest()
