import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


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
