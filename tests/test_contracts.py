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


def test_release_metadata_binds_current_rev03_manuscript_pair():
    scope = (Path(__file__).resolve().parents[1] / "MANUSCRIPT_SCOPE.md").read_text(encoding="utf-8")
    assert "green_methanol_manuscript_references_v02_2026-08-14_rev03_data_code_2026-08-22.docx" in scope
    assert "green_methanol_supplementary_information_rev03_data_code_2026-08-22.docx" in scope
    assert "FAB8876EF06DA0A48F7D8B102FA51AD3A8D97515A6BF264635AEC0F387D64D0B" in scope
    assert "DA53964D3AC2CEB38D266D8EBE62016BADEF7AA23A9FA6DAE58284B42A406A3D" in scope


def test_ci_manifest_entrypoint_exists():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "python scripts/build_manifest.py" in workflow
    assert (root / "scripts" / "build_manifest.py").is_file()


def test_release_status_requires_external_publication_gates_and_author_confirmation():
    status_path = Path(__file__).resolve().parents[1] / "RELEASE_STATUS.md"
    assert status_path.is_file()
    status = status_path.read_text(encoding="utf-8")
    assert "https://github.com/Chenzhongdaji/green-methanol-pipeline-reuse-public" in status
    assert "release candidate" in status.casefold()
    assert "NOT_REPRODUCED" in status
    assert "author confirmation" in status.casefold()
    assert "doi" in status.casefold()
