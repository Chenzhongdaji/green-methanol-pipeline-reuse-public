from pathlib import Path

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


def test_release_status_requires_external_publication_gates_and_author_confirmation():
    status_path = Path(__file__).resolve().parents[1] / "RELEASE_STATUS.md"
    assert status_path.is_file()
    status = status_path.read_text(encoding="utf-8")
    assert "https://github.com/Chenzhongdaji/green-methanol-pipeline-reuse-public" in status
    assert "full workflow" in status.casefold()
    assert "NOT_REPRODUCED" not in status
    assert "Figure 2e" in status
    assert "data/output_registry.csv" in status
