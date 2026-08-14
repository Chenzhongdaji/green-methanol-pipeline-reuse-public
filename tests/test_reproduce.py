import json
from pathlib import Path
import shutil

from green_methanol_release.reproduce import run_reproduction


ROOT = Path(__file__).resolve().parents[1]


def test_smoke_reproduces_open_aggregate_scope(tmp_path):
    report = run_reproduction(ROOT, "smoke", tmp_path / "run.json")
    assert report["status"] == "PASS"
    assert report["level_1_status"] == "PASS"
    assert report["level_2_status"] == "NOT_REPRODUCED"
    assert report["workflows"]["figure_source_data"] == "aggregate-only"


def test_full_stops_without_controlled_inputs(tmp_path):
    report = run_reproduction(ROOT, "full", tmp_path / "run.json")
    assert report["status"] == "NOT_REPRODUCED"
    assert "exact directed pipeline topology" in report["level_2_reason"]


def test_report_is_external_and_records_commit(tmp_path):
    output = tmp_path / "run.json"
    report = run_reproduction(ROOT, "smoke", output)
    assert json.loads(output.read_text(encoding="utf-8"))["release_commit"] == report["release_commit"]
    assert not (ROOT / "run.json").exists()


def test_public_payloads_are_utf8_clean():
    paths = [
        ROOT / "figures" / "source_data" / "figure-01.csv",
        ROOT / "figures" / "source_data" / "figure-03.csv",
        ROOT / "figures" / "source_data" / "figure-04.csv",
        ROOT / "figures" / "source_data" / "figure-05.csv",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "鈥" not in text
        assert "\ufffd" not in text


def test_dictionary_column_coverage_is_fail_closed(tmp_path):
    root = tmp_path / "release"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
    dictionary = root / "data" / "dictionaries" / "figure_03.md"
    dictionary.write_text(
        dictionary.read_text(encoding="utf-8").replace("pipeline_tonne_km", "pipeline_tonne_km_missing"),
        encoding="utf-8",
        newline="\n",
    )
    report = run_reproduction(root, "smoke", tmp_path / "run.json")
    assert report["status"] == "FAIL"
    assert report["level_1_status"] == "FAIL"
