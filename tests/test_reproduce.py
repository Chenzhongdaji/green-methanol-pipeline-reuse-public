import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

from green_methanol_release import pipeline as pipeline_module
from green_methanol_release import reproduce as reproduce_module
from green_methanol_release.inventory import DATASET_REGISTRY_FIELDS, OUTPUT_REGISTRY_FIELDS
from green_methanol_release.reproduce import run_reproduction


ROOT = Path(__file__).resolve().parents[1]
_ABSOLUTE_PATH_RE = re.compile(
    r"(?i)(?:\b[A-Z]:[\\/]|(?<![\w])\\\\[^\\/\s\"',$}]+[\\/][^\\/\s\"',$}]+|(?:^|[\s\"'=:(])/(?:home|Users|root)/)"
)


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _minimal_output_row(
    output_id: str,
    expected_artifact: str,
    *,
    input_path: str = "data/carrier.csv",
    command: str | None = None,
) -> dict[str, str]:
    return {
        "output_id": output_id,
        "manuscript_location": output_id,
        "generation_command": command
        or (
            "python scripts/build_output.py --input "
            f"{input_path} --output {expected_artifact} --label {output_id}"
        ),
        "input_dataset_ids": "carrier-1",
        "expected_artifact": expected_artifact,
    }


def _minimal_release(
    tmp_path: Path,
    output_rows: list[dict[str, str]] | None = None,
    *,
    carrier_path: str = "data/carrier.csv",
) -> Path:
    root = tmp_path / "minimal-release"
    carrier = root / Path(*carrier_path.split("/"))
    carrier.parent.mkdir(parents=True, exist_ok=True)
    carrier.write_text("safe carrier\n", encoding="utf-8", newline="\n")
    builder = root / "scripts" / "build_output.py"
    builder.parent.mkdir(parents=True, exist_ok=True)
    builder.write_text(
        "import argparse\n"
        "from pathlib import Path\n"
        "import sys\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--input', required=True)\n"
        "parser.add_argument('--output', required=True)\n"
        "parser.add_argument('--label', required=True)\n"
        "parser.add_argument('--exit-code', type=int, default=0)\n"
        "parser.add_argument('--skip', action='store_true')\n"
        "args = parser.parse_args()\n"
        "Path(args.input).read_text(encoding='utf-8')\n"
        "print(args.label, flush=True)\n"
        "if args.exit_code:\n"
        "    raise SystemExit(args.exit_code)\n"
        "if not args.skip:\n"
        "    output = Path(args.output)\n"
        "    output.parent.mkdir(parents=True, exist_ok=True)\n"
        "    output.write_text(args.label + chr(10), encoding='utf-8', newline=chr(10))\n",
        encoding="utf-8",
        newline="\n",
    )
    digest = hashlib.sha256(carrier.read_bytes()).hexdigest()
    dataset_rows = [
        {
            "dataset_id": "carrier-1",
            "public_path": carrier_path,
            "role": "terminal source carrier",
            "origin": "author-generated",
            "access_route": "repository carrier",
            "license": "CC BY 4.0",
            "sha256": digest,
            "acquisition_command": "",
            "processing_command": "",
            "manuscript_uses": "temporary test fixture",
            "source_relative_path": "",
            "stage_action": "existing",
        }
    ]
    if output_rows is None:
        output_rows = [
            _minimal_output_row("first", "figures/first.png"),
            _minimal_output_row("second", "figures/second.png"),
        ]
    _write_csv(root / "data" / "dataset_registry.csv", DATASET_REGISTRY_FIELDS, dataset_rows)
    _write_csv(root / "data" / "output_registry.csv", OUTPUT_REGISTRY_FIELDS, output_rows)
    return root


def _rewrite_output_registry(root: Path, rows: list[dict[str, str]]) -> None:
    _write_csv(root / "data" / "output_registry.csv", OUTPUT_REGISTRY_FIELDS, rows)


def _rewrite_dataset_registry(root: Path, rows: list[dict[str, str]]) -> None:
    _write_csv(root / "data" / "dataset_registry.csv", DATASET_REGISTRY_FIELDS, rows)


def test_smoke_reproduces_open_aggregate_scope(tmp_path):
    report = run_reproduction(ROOT, "smoke", tmp_path / "run.json")
    assert report["status"] == "PASS"
    assert report["workflows"]["figure_source_data"] == "aggregate-only"


def test_full_real_release_executes_all_registered_outputs(tmp_path):
    report = run_reproduction(ROOT, "full", tmp_path / "run.json")
    expected_ids = [
        "figure-01",
        "figure-02a-d-f-h",
        "figure-02e",
        "figure-03",
        "figure-04",
        "figure-05",
    ]
    assert report["status"] == "PASS"
    assert report["executed_output_ids"] == expected_ids
    assert set(report["artifacts"]) == set(expected_ids)
    assert all(len(item["sha256"]) == 64 for item in report["artifacts"].values())
    report_text = (tmp_path / "full_reproduction.json").read_text(encoding="utf-8")
    log_paths = sorted((tmp_path / "logs").glob("*.log"))
    log_text = "\n".join(path.read_text(encoding="utf-8") for path in log_paths)
    combined_text = report_text + "\n" + log_text
    assert len(log_paths) == len(expected_ids)
    assert "NOT_REPRODUCED" not in combined_text
    assert _ABSOLUTE_PATH_RE.search(combined_text) is None


def test_full_real_release_repeats_with_identical_artifact_hashes(tmp_path):
    first = run_reproduction(ROOT, "full", tmp_path / "first.json")
    second = run_reproduction(ROOT, "full", tmp_path / "second.json")

    assert first["status"] == "PASS"
    assert second["status"] == "PASS"
    assert first["executed_output_ids"] == second["executed_output_ids"]
    assert first["artifacts"] == second["artifacts"]


def test_full_runs_outputs_in_registry_order_and_reports_exact_artifacts(tmp_path):
    root = _minimal_release(tmp_path)
    requested = tmp_path / "requested.json"

    report = run_reproduction(root, "full", requested)

    first = root / "figures" / "first.png"
    second = root / "figures" / "second.png"
    assert report["status"] == "PASS"
    assert report["executed_output_ids"] == ["first", "second"]
    assert report["command_return_codes"] == {"first": 0, "second": 0}
    assert report["artifacts"] == {
        "first": {
            "path": "figures/first.png",
            "sha256": hashlib.sha256(first.read_bytes()).hexdigest(),
        },
        "second": {
            "path": "figures/second.png",
            "sha256": hashlib.sha256(second.read_bytes()).hexdigest(),
        },
    }
    assert json.loads(requested.read_text(encoding="utf-8")) == report
    assert json.loads(
        (tmp_path / "full_reproduction.json").read_text(encoding="utf-8")
    ) == report
    assert (tmp_path / "logs" / "first.log").is_file()
    assert (tmp_path / "logs" / "second.log").is_file()
    assert str(root) not in (tmp_path / "full_reproduction.json").read_text(encoding="utf-8")


def test_full_fails_on_nonzero_builder_exit(tmp_path):
    row = _minimal_output_row(
        "bad",
        "figures/bad.png",
        command=(
            "python scripts/build_output.py --input data/carrier.csv "
            "--output figures/bad.png --label bad --exit-code 7"
        ),
    )
    root = _minimal_release(tmp_path, [row])

    report = run_reproduction(root, "full", tmp_path / "nonzero.json")

    assert report["status"] == "FAIL"
    assert report["executed_output_ids"] == ["bad"]
    assert report["command_return_codes"] == {"bad": 7}
    assert "return code 7" in report["error"]


def test_full_fails_before_execution_when_builder_is_missing(tmp_path):
    row = _minimal_output_row(
        "missing",
        "figures/missing.png",
        command=(
            "python scripts/not_present.py --input data/carrier.csv "
            "--output figures/missing.png --label missing"
        ),
    )
    root = _minimal_release(tmp_path, [row])

    report = run_reproduction(root, "full", tmp_path / "missing-builder.json")

    assert report["status"] == "FAIL"
    assert report["executed_output_ids"] == []
    assert report["command_return_codes"] == {}
    assert "not_present.py" in report["error"]


def test_full_fails_when_builder_does_not_create_expected_artifact(tmp_path):
    row = _minimal_output_row(
        "no-artifact",
        "figures/no-artifact.png",
        command=(
            "python scripts/build_output.py --input data/carrier.csv "
            "--output figures/no-artifact.png --label no-artifact --skip"
        ),
    )
    root = _minimal_release(tmp_path, [row])

    report = run_reproduction(root, "full", tmp_path / "missing-artifact.json")

    assert report["status"] == "FAIL"
    assert report["executed_output_ids"] == ["no-artifact"]
    assert report["command_return_codes"] == {"no-artifact": 0}
    assert "expected artifact" in report["error"]


def test_full_checks_carrier_hashes_before_execution(tmp_path):
    row = _minimal_output_row("should-not-run", "figures/should-not-run.png")
    root = _minimal_release(tmp_path, [row])
    (root / "data" / "carrier.csv").write_text("tampered\n", encoding="utf-8", newline="\n")

    report = run_reproduction(root, "full", tmp_path / "hash-mismatch.json")

    assert report["status"] == "FAIL"
    assert report["executed_output_ids"] == []
    assert report["command_return_codes"] == {}
    assert "sha256" in report["error"]
    assert not (root / "figures" / "should-not-run.png").exists()


def test_full_rejects_forbidden_registered_path_without_accessing_it(tmp_path):
    row = _minimal_output_row(
        "forbidden",
        "figures/forbidden.png",
        input_path="data/管道数据/secret.csv",
    )
    root = _minimal_release(tmp_path, [row], carrier_path="data/carrier.csv")
    datasets = [
        {
            "dataset_id": "carrier-1",
            "public_path": "data/管道数据/secret.csv",
            "role": "terminal source carrier",
            "origin": "author-generated",
            "access_route": "repository carrier",
            "license": "CC BY 4.0",
            "sha256": "a" * 64,
            "acquisition_command": "",
            "processing_command": "",
            "manuscript_uses": "temporary test fixture",
            "source_relative_path": "",
            "stage_action": "existing",
        }
    ]
    _rewrite_dataset_registry(root, datasets)

    report = run_reproduction(root, "full", tmp_path / "forbidden.json")

    assert report["status"] == "FAIL"
    assert report["executed_output_ids"] == []
    assert "path" in report["error"]


def test_full_rejects_command_script_outside_scripts(tmp_path):
    row = _minimal_output_row(
        "outside",
        "figures/outside.png",
        command=(
            "python build_output.py --input data/carrier.csv "
            "--output figures/outside.png --label outside"
        ),
    )
    root = _minimal_release(tmp_path, [row])

    report = run_reproduction(root, "full", tmp_path / "outside-script.json")

    assert report["status"] == "FAIL"
    assert report["executed_output_ids"] == []
    assert "scripts/" in report["error"]


def test_full_rejects_shell_metacharacters(tmp_path):
    row = _minimal_output_row(
        "shell",
        "figures/shell.png",
        command=(
            "python scripts/build_output.py --input data/carrier.csv "
            "--output figures/shell.png --label shell;"
        ),
    )
    root = _minimal_release(tmp_path, [row])

    report = run_reproduction(root, "full", tmp_path / "shell.json")

    assert report["status"] == "FAIL"
    assert report["executed_output_ids"] == []
    assert "shell metacharacter" in report["error"]


def test_full_stops_after_first_builder_failure(tmp_path):
    rows = [
        _minimal_output_row(
            "first-bad",
            "figures/first-bad.png",
            command=(
                "python scripts/build_output.py --input data/carrier.csv "
                "--output figures/first-bad.png --label first-bad --exit-code 3"
            ),
        ),
        _minimal_output_row("second-good", "figures/second-good.png"),
    ]
    root = _minimal_release(tmp_path, rows)

    report = run_reproduction(root, "full", tmp_path / "stop.json")

    assert report["status"] == "FAIL"
    assert report["executed_output_ids"] == ["first-bad"]
    assert report["command_return_codes"] == {"first-bad": 3}
    assert not (root / "figures" / "second-good.png").exists()


def test_full_reproduction_delegates_before_resolving_or_creating_output_parent(
    tmp_path, monkeypatch
):
    root = _minimal_release(tmp_path)
    requested = tmp_path / "delegated" / "requested.json"
    events: list[str] = []
    original_resolve = Path.resolve
    original_mkdir = Path.mkdir

    def fake_run_full(received_root: Path, received_output_root: Path) -> dict[str, object]:
        events.append("run_full")
        assert received_root == root
        assert received_output_root == requested.parent
        return {
            "status": "PASS",
            "mode": "full",
        }

    def record_resolve(path: Path, *args, **kwargs) -> Path:
        events.append("resolve")
        return original_resolve(path, *args, **kwargs)

    def record_mkdir(path: Path, *args, **kwargs):
        events.append("mkdir")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(reproduce_module, "run_full", fake_run_full)
    monkeypatch.setattr(Path, "resolve", record_resolve)
    monkeypatch.setattr(Path, "mkdir", record_mkdir)

    report = run_reproduction(root, "full", requested)

    assert report["status"] == "PASS"
    assert events[0] == "run_full"
    assert "mkdir" not in events[: events.index("run_full") + 1]
    assert requested.is_file()


def test_full_invalid_root_returns_fail_report_instead_of_raising(tmp_path):
    missing_root = tmp_path / "missing-release"

    report = pipeline_module.run_full(missing_root, tmp_path / "output")

    assert report["status"] == "FAIL"
    assert report["error"]


def test_full_rejects_output_inside_release_without_touching_report_path(tmp_path):
    root = _minimal_release(tmp_path)
    report_path = root / "full_reproduction.json"

    report = pipeline_module.run_full(root, root)

    assert report["status"] == "FAIL"
    assert not report_path.exists()


def test_full_rejects_unsafe_report_path_without_touching_it(tmp_path):
    root = _minimal_release(tmp_path)
    unsafe_output = tmp_path / "管道数据" / "output"

    report = pipeline_module.run_full(root, unsafe_output)

    assert report["status"] == "FAIL"
    assert not unsafe_output.exists()


@pytest.mark.parametrize("character", ["*", "?", "[", "]", "~", "#"])
def test_full_rejects_additional_shell_metacharacters(tmp_path, character):
    row = _minimal_output_row(
        "shell-extra",
        "figures/shell-extra.png",
        command=(
            "python scripts/build_output.py --input data/carrier.csv "
            f"--output figures/shell-extra.png --label shell-extra{character}"
        ),
    )
    root = _minimal_release(tmp_path, [row])

    report = run_reproduction(root, "full", tmp_path / f"shell-{ord(character)}.json")

    assert report["status"] == "FAIL"
    assert report["executed_output_ids"] == []
    assert "shell metacharacter" in report["error"]


@pytest.mark.parametrize(
    "input_path",
    [
        "C:" + "/outside.csv",
        "../carrier.csv",
        "data/unregistered.csv",
    ],
)
def test_full_rejects_absolute_parent_or_unregistered_input(tmp_path, input_path):
    row = _minimal_output_row(
        "bad-input",
        "figures/bad-input.png",
        input_path=input_path,
    )
    root = _minimal_release(tmp_path, [row])

    report = run_reproduction(root, "full", tmp_path / "bad-input.json")

    assert report["status"] == "FAIL"
    assert report["executed_output_ids"] == []
    assert report["command_return_codes"] == {}
    assert report["error"]


def test_full_does_not_record_output_when_subprocess_cannot_start(tmp_path, monkeypatch):
    root = _minimal_release(
        tmp_path,
        [_minimal_output_row("cannot-start", "figures/cannot-start.png")],
    )

    def fail_to_start(*args, **kwargs):
        raise OSError("cannot start builder")

    monkeypatch.setattr(pipeline_module.subprocess, "run", fail_to_start)
    report = run_reproduction(root, "full", tmp_path / "cannot-start.json")

    assert report["status"] == "FAIL"
    assert report["executed_output_ids"] == []
    assert report["command_return_codes"] == {}
    assert "cannot start builder" in report["error"]


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
    assert "not valid CSV" in report["errors"][0]


def test_non_git_copy_cannot_report_level1_pass(tmp_path):
    root = _copy_release_without_git(tmp_path)
    report = run_reproduction(root, "smoke", tmp_path / "nogit.json")
    assert report["status"] == "FAIL"
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
    assert report["release_commit"] == "unrecorded"


def test_chinese_release_root_git_head_decodes_without_pythonutf8(tmp_path):
    env = os.environ.copy()
    env.pop("PYTHONUTF8", None)
    output = tmp_path / "chinese-root.json"
    completed = subprocess.run(
        [sys.executable, "scripts/reproduce.py", "--mode", "smoke", "--output", str(output)],
        cwd=ROOT,
        env=env,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert len(report["release_commit"]) == 40


@pytest.mark.parametrize("filename", ["public_sources.csv", "dataset_registry.csv"])
def test_inventory_crlf_mutation_is_fail_closed(tmp_path, filename):
    root = _copy_release(tmp_path, filename.replace(".csv", ""))
    path = root / "data" / filename
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    report = run_reproduction(root, "smoke", tmp_path / f"{filename}.json")
    assert report["status"] == "FAIL"


def test_duplicate_headline_claim_id_is_rejected_even_when_set_matches(tmp_path):
    root = _copy_release(tmp_path)
    path = root / "qa" / "expected" / "headline_claims.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines.append(lines[1])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    report = run_reproduction(root, "smoke", tmp_path / "duplicate-claim.json")
    assert report["status"] == "FAIL"


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


def test_panel_map_requires_existing_pairings_and_figure_coverage(tmp_path):
    root = _copy_release(tmp_path)
    path = root / "figures" / "panel_map.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    first = lines[1].split(",")
    first[4] = "data/dictionaries/missing.md"
    lines[1] = ",".join(first)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    report = run_reproduction(root, "smoke", tmp_path / "panel-map.json")
    assert report["status"] == "FAIL"


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


def test_dictionary_rejects_unknown_structural_column_row(tmp_path):
    root = _copy_release(tmp_path)
    path = root / "data" / "dictionaries" / "figure_03.md"
    text = path.read_text(encoding="utf-8")
    text += "\n| unexpected_column | test definition | not_applicable | blank forbidden | test derivation | test panel |\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    report = run_reproduction(root, "smoke", tmp_path / "dictionary-extra-row.json")
    assert report["status"] == "FAIL"


@pytest.mark.parametrize(
    ("column", "replacement"),
    [
        ("metric", "share"),
        ("tolerance", "999"),
        ("expected_value", "52.25"),
        ("evidence_boundary", "spoofed evidence boundary"),
    ],
)
def test_headline_claim_rows_are_immutable(tmp_path, column, replacement):
    root = _copy_release(tmp_path, f"claim-{column}")
    path = root / "qa" / "expected" / "headline_claims.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0][column] = replacement
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    report = run_reproduction(root, "smoke", tmp_path / f"claim-{column}.json")
    assert report["status"] == "FAIL"


def test_non_reproduced_workflows_have_explicit_reasons(tmp_path):
    report = run_reproduction(ROOT, "smoke", tmp_path / "workflow-reasons.json")
    reasons = report["workflow_reasons"]
    assert set(reasons) == {"figure_source_data", "manuscript_artifacts", "network_model"}
    assert all(isinstance(value, str) and value.strip() for value in reasons.values())


@pytest.mark.parametrize(
    "name",
    [
        "figure_01.md",
        "figure2_aggregate_source.md",
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


def test_metadata_dictionaries_describe_provenance_boundaries():
    public_sources = (ROOT / "data" / "dictionaries" / "public_sources.md").read_text(encoding="utf-8")
    dataset_registry = (ROOT / "data" / "dictionaries" / "dataset_registry.md").read_text(encoding="utf-8")
    output_registry = (ROOT / "data" / "dictionaries" / "output_registry.md").read_text(encoding="utf-8")
    assert "does not grant redistribution rights" in public_sources
    assert "repository grant is not inferred" in dataset_registry
    assert "dataset identifiers it consumes" in output_registry


def test_dictionary_missing_codes_match_released_blanks():
    figure_01 = (ROOT / "data" / "dictionaries" / "figure_01.md").read_text(encoding="utf-8")
    panel_map = (ROOT / "data" / "dictionaries" / "panel_map.md").read_text(encoding="utf-8")
    registry = (ROOT / "data" / "dictionaries" / "dataset_registry.md").read_text(encoding="utf-8")
    assert "| target |" in figure_01 and "text or blank for terminal stage" in figure_01
    assert "| source_data |" in panel_map and "POSIX path or blank" in panel_map
    assert "| dictionary |" in panel_map and "POSIX path or blank" in panel_map
    assert "| sha256 |" in registry and "64 lowercase hexadecimal" in registry
