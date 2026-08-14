import json
from pathlib import Path
import shutil
import subprocess

import pytest

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


@pytest.mark.parametrize(
    "name",
    ["figure-01.csv", "figure-03.csv", "figure-04.csv", "figure-05.csv"],
)
def test_every_figure_schema_rejects_restricted_identifier_columns(tmp_path, name):
    root = tmp_path / name.replace(".csv", "")
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
    path = root / "figures" / "source_data" / name
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0] + ",node_id"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    report = run_reproduction(root, "smoke", tmp_path / f"{name}.json")
    assert report["status"] == "FAIL"
    assert report["level_1_status"] == "FAIL"


def _copy_release_without_git(tmp_path, name="release"):
    root = tmp_path / name
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
    return root


def _copy_release(tmp_path, name="release"):
    root = tmp_path / name
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".venv", "__pycache__"))
    return root


def test_unclosed_quote_is_fail_closed_during_full_csv_iteration(tmp_path):
    root = _copy_release(tmp_path)
    path = root / "figures" / "source_data" / "figure-03.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].rsplit(",", 1)[0] + ',"1918444'
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    report = run_reproduction(root, "smoke", tmp_path / "unclosed.json")
    assert report["status"] == "FAIL"
    assert report["level_1_status"] == "FAIL"
    assert "not valid CSV" in report["errors"][0]


def test_non_git_copy_cannot_report_level1_pass(tmp_path):
    root = _copy_release_without_git(tmp_path)
    report = run_reproduction(root, "smoke", tmp_path / "nogit.json")
    assert report["status"] == "FAIL"
    assert report["level_1_status"] == "FAIL"
    assert report["release_commit"] == "unrecorded"


def test_nested_release_cannot_inherit_parent_git_commit(tmp_path):
    parent = tmp_path / "parent-git"
    parent.mkdir()
    root = parent / "nested-release"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
    subprocess.run(["git", "init", "-q"], cwd=parent, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=parent, check=True)
    subprocess.run(["git", "config", "user.name", "Task 3 test"], cwd=parent, check=True)
    subprocess.run(["git", "add", "nested-release"], cwd=parent, check=True)
    subprocess.run(["git", "commit", "-qm", "parent fixture"], cwd=parent, check=True)
    report = run_reproduction(root, "smoke", tmp_path / "nested-parent.json")
    assert report["status"] == "FAIL"
    assert report["level_1_status"] == "FAIL"
    assert report["release_commit"] == "unrecorded"


@pytest.mark.parametrize("filename", ["public_sources.csv", "controlled_inputs_metadata.csv"])
def test_inventory_crlf_mutation_is_fail_closed(tmp_path, filename):
    root = _copy_release(tmp_path, filename.replace(".csv", ""))
    path = root / "data" / filename
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    report = run_reproduction(root, "smoke", tmp_path / f"{filename}.json")
    assert report["status"] == "FAIL"
    assert report["level_1_status"] == "FAIL"


def test_duplicate_headline_claim_id_is_rejected_even_when_set_matches(tmp_path):
    root = _copy_release(tmp_path)
    path = root / "qa" / "expected" / "headline_claims.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines.append(lines[1])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    report = run_reproduction(root, "smoke", tmp_path / "duplicate-claim.json")
    assert report["status"] == "FAIL"
    assert report["level_1_status"] == "FAIL"


def test_extra_terminal_account_row_is_rejected(tmp_path):
    root = _copy_release(tmp_path)
    path = root / "data" / "author_derived" / "terminal_gap_aggregate.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines.append(
        "extra_scope,mid,2060,demand_weighted,1,0,1,0,closed,extra row must not be accepted"
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    report = run_reproduction(root, "smoke", tmp_path / "extra-account.json")
    assert report["status"] == "FAIL"
    assert report["level_1_status"] == "FAIL"


def test_panel_map_requires_exact_allowed_rows_and_pairings(tmp_path):
    root = _copy_release(tmp_path)
    path = root / "figures" / "panel_map.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    first = lines[1].split(",")
    third = lines[3].split(",")
    first[4], third[4] = third[4], first[4]
    lines[1] = ",".join(first)
    lines[3] = ",".join(third)
    lines.append("Figure 6,all,not-run,,,unexpected figure")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    report = run_reproduction(root, "smoke", tmp_path / "panel-map.json")
    assert report["status"] == "FAIL"
    assert report["level_1_status"] == "FAIL"


def test_dictionary_row_deletion_is_rejected_even_when_field_token_remains(tmp_path):
    root = _copy_release(tmp_path)
    path = root / "data" / "dictionaries" / "figure_03.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    removed = next(line for line in lines if line.startswith("| distance_km |"))
    lines.remove(removed)
    lines.append("The distance_km field remains named in this narrative.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    report = run_reproduction(root, "smoke", tmp_path / "dictionary-row.json")
    assert report["status"] == "FAIL"
    assert report["level_1_status"] == "FAIL"


def test_non_reproduced_workflows_have_explicit_reasons(tmp_path):
    report = run_reproduction(ROOT, "smoke", tmp_path / "workflow-reasons.json")
    reasons = report["workflow_reasons"]
    assert set(reasons) == {"figure_source_data", "manuscript_artifacts", "network_model"}
    assert all(isinstance(value, str) and value.strip() for value in reasons.values())


@pytest.mark.parametrize(
    "name",
    [
        "figure_01.md",
        "figure_03.md",
        "figure_04.md",
        "figure_05.md",
        "headline_claims.md",
        "panel_map.md",
        "terminal_gap_aggregate.md",
    ],
)
def test_cc_by_intended_carriers_are_explicitly_labelled(name):
    text = (ROOT / "data" / "dictionaries" / name).read_text(encoding="utf-8")
    assert "author-generated aggregate data" in text


@pytest.mark.parametrize("name", ["public_sources.md", "controlled_inputs.md"])
def test_metadata_dictionaries_do_not_claim_cc_by(name):
    text = (ROOT / "data" / "dictionaries" / name).read_text(encoding="utf-8")
    assert "author-generated aggregate data" not in text


def test_dictionary_missing_codes_match_released_blanks():
    figure_01 = (ROOT / "data" / "dictionaries" / "figure_01.md").read_text(encoding="utf-8")
    panel_map = (ROOT / "data" / "dictionaries" / "panel_map.md").read_text(encoding="utf-8")
    controlled = (ROOT / "data" / "dictionaries" / "controlled_inputs.md").read_text(encoding="utf-8")
    assert "| target |" in figure_01 and "text or blank for terminal stage" in figure_01
    assert "| source_data |" in panel_map and "POSIX path or blank" in panel_map
    assert "| dictionary |" in panel_map and "POSIX path or blank" in panel_map
    assert "| sha256 |" in controlled and "64 lowercase hexadecimal or blank" in controlled
