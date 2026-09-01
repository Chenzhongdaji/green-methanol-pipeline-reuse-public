from pathlib import Path
import re

import pytest

from green_methanol_release.contracts import (
    ALLOWED_WORKFLOW_STATUSES,
    ReleaseRoot,
    safe_relative_path,
    validate_status,
)


def test_status_vocabulary_is_closed():
    assert ALLOWED_WORKFLOW_STATUSES == {
        "reproduced", "aggregate-only", "hash-only", "not-run"
    }
    with pytest.raises(ValueError, match="unsupported workflow status"):
        validate_status("PASS")


@pytest.mark.parametrize(
    "value",
    [
        "../secret.csv",
        "C:" + "/" + "Users/name/file.csv",
        "/" + "home/name/file",
        r"folder\file.csv",
        "\\\\" + "server" + "\\share\\file.csv",
    ],
)
def test_safe_relative_path_rejects_escape_and_absolute_paths(value):
    with pytest.raises(ValueError):
        safe_relative_path(value)


def test_release_root_refuses_writes_outside_root(tmp_path: Path):
    root = ReleaseRoot(tmp_path / "release")
    assert root.resolve("data/file.csv") == (tmp_path / "release" / "data" / "file.csv").resolve()
    with pytest.raises(ValueError):
        root.resolve("../outside.txt")


def test_release_metadata_binds_current_rev04_manuscript_pair():
    scope = (Path(__file__).resolve().parents[1] / "MANUSCRIPT_SCOPE.md").read_text(encoding="utf-8")
    assert "green_methanol_manuscript_references_v02_2026-08-14_rev04_public_data_code_2026-08-22.docx" in scope
    assert "green_methanol_supplementary_information_rev04_public_data_code_2026-08-22.docx" in scope
    assert "9A93C3FE87F86426D79466872F910A861B8AF06543AA3C4B4B0BD0A258499458" in scope
    assert "94379F97A40120353EC70762B2C305774865EEE5CA9281B8C5CFFA213F1C1CF0" in scope


def test_ci_manifest_entrypoint_exists():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "python scripts/build_manifest.py" in workflow
    assert workflow.count("python scripts/build_manifest.py") >= 2
    assert workflow.count("python scripts/reproduce.py --mode full") >= 2
    assert "cmp" in workflow
    assert "green-methanol-full-1/full_reproduction.json" in workflow
    assert "green-methanol-full-2/full_reproduction.json" in workflow
    assert workflow.count("full_reproduction.json") >= 3
    assert (root / "scripts" / "build_manifest.py").is_file()


def test_runtime_has_five_identical_pinned_dependencies():
    root = Path(__file__).resolve().parents[1]
    expected = {
        "numpy": "2.5.1",
        "pandas": "3.0.1",
        "matplotlib": "3.11.1",
        "networkx": "3.5",
        "pytest": "8.4.2",
    }
    requirements = (root / "environment" / "requirements.txt").read_text(encoding="utf-8")
    requirement_pins = dict(
        line.split("==", 1)
        for line in requirements.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    assert requirement_pins == expected

    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    for name, version in expected.items():
        assert f'"{name}=={version}"' in pyproject

    environment = (root / "environment" / "environment.md").read_text(encoding="utf-8")
    assert "five pinned dependencies" in environment
    assert "two pinned requirements" not in environment
    for name, version in expected.items():
        assert f"`{name}=={version}`" in environment


def test_release_docs_describe_output_as_a_report_file():
    root = Path(__file__).resolve().parents[1]
    for relative in ("README.md", "DATA_AVAILABILITY.md", "CODE_AVAILABILITY.md", "RELEASE_STATUS.md"):
        text = (root / relative).read_text(encoding="utf-8")
        assert "full_reproduction.json" in text or "report file" in text.casefold()
    readme = (root / "README.md").read_text(encoding="utf-8")
    code = (root / "CODE_AVAILABILITY.md").read_text(encoding="utf-8")
    status = (root / "RELEASE_STATUS.md").read_text(encoding="utf-8")
    assert "--output <external-output>/green-methanol-full/full_reproduction.json" in readme
    assert "--output <external-output>/green-methanol-full/full_reproduction.json" in code
    assert "--output <external-output>/green-methanol-full/full_reproduction.json" in status
    assert re.search(r"--output[^\n]*green-methanol-full[^\n]*full_reproduction\.json", readme)


def test_release_status_requires_external_publication_gates_and_author_confirmation():
    status_path = Path(__file__).resolve().parents[1] / "RELEASE_STATUS.md"
    assert status_path.is_file()
    status = status_path.read_text(encoding="utf-8")
    assert "https://github.com/Chenzhongdaji/green-methanol-pipeline-reuse-public" in status
    assert "full workflow" in status.casefold()
    assert "NOT_REPRODUCED" not in status
    assert "Figure 2e" in status
    assert "data/output_registry.csv" in status
