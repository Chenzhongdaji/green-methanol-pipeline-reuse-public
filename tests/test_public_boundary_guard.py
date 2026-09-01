from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_COMPONENT = "\u7ba1\u9053\u6570\u636e"


def _load_guard_module():
    path = ROOT / "scripts" / "check_public_boundary.py"
    assert path.is_file()
    spec = importlib.util.spec_from_file_location("check_public_boundary", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gitignore_excludes_only_exact_private_directory_components():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert f"**/{FORBIDDEN_COMPONENT}/" in gitignore
    assert f"**/{FORBIDDEN_COMPONENT}\u8bf4\u660e/" not in gitignore

    exact = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"],
        cwd=ROOT,
        input=f"src/{FORBIDDEN_COMPONENT}/payload.csv\n",
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    near = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"],
        cwd=ROOT,
        input=f"src/{FORBIDDEN_COMPONENT}\u8bf4\u660e/payload.csv\n",
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    assert exact.returncode == 0
    assert near.returncode != 0


def test_precommit_guard_is_exact_component_and_index_fail_closed():
    guard = _load_guard_module()
    paths = [
        f"src/{FORBIDDEN_COMPONENT}/payload.csv",
        f"src/{FORBIDDEN_COMPONENT}\u8bf4\u660e/payload.csv",
        "data/public.csv",
    ]

    assert guard.forbidden_paths(paths) == [
        f"src/{FORBIDDEN_COMPONENT}/payload.csv"
    ]
    assert "--cached" in (ROOT / "scripts" / "check_public_boundary.py").read_text(
        encoding="utf-8"
    )


def test_precommit_guard_is_configured_and_documented():
    config = ROOT / ".pre-commit-config.yaml"
    assert config.is_file()
    config_text = config.read_text(encoding="utf-8")
    assert "check_public_boundary.py" in config_text
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "pre-commit install" in readme
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "check_public_boundary.py" in workflow
