"""Fail-closed orchestration for full public-release reproduction."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import sys
from typing import Any

from .contracts import ReleaseRoot, safe_relative_path
from .inventory import (
    load_dataset_registry,
    load_output_registry,
    validate_release_registry,
)
from .safety import assert_public_path, resolve_public_path


_REGISTRY_PATHS = (
    "data/dataset_registry.csv",
    "data/output_registry.csv",
)
_CARRIER_ACTIONS = frozenset({"copy", "existing", "acquire"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SHELL_METACHARACTERS = frozenset(
    ";&|<>$`(){}!'\"*?[]~#" + chr(92) + chr(13) + chr(10)
)
_UNC_ABSOLUTE = re.compile(
    r"(?<![A-Za-z0-9_])\\\\[^\\/\s,;]+[\\/][^\\/\s,;]+(?:[\\/][^\s,;]*)?"
)
_WINDOWS_ABSOLUTE = re.compile(r"(?i)(?<![a-z0-9_])[a-z]:[^\s,;]+")
_POSIX_ABSOLUTE = re.compile(r"(?<![a-z0-9_])/(?:[^\s,;]+)")
_CHECKSUM_LINE = re.compile(r"^([0-9a-f]{64})  ([^\r\n]+)$")
_FROZEN_MANIFEST_FIELDS = (
    "path",
    "bytes",
    "sha256",
    "purpose",
    "licence_scope",
    "data_class",
)


def _sha256(path: Path) -> str:
    path = resolve_public_path(Path(path).parent, Path(path))
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _redact_paths(value: object, root: Path, output_root: Path) -> str:
    """Keep diagnostics useful without placing absolute paths in the report."""

    text = str(value)
    replacements = (
        (str(root), "<release-root>"),
        (root.as_posix(), "<release-root>"),
        (str(output_root), "<output-root>"),
        (output_root.as_posix(), "<output-root>"),
    )
    for source, replacement in replacements:
        text = text.replace(source, replacement)
    text = _UNC_ABSOLUTE.sub("<absolute-path>", text)
    text = _WINDOWS_ABSOLUTE.sub("<absolute-path>", text)
    text = _POSIX_ABSOLUTE.sub("<absolute-path>", text)
    text = text.replace("NOT_REPRODUCED", "not-reproduced")
    return text


def _safe_repo_path(root: Path, value: str, label: str) -> tuple[str, Path]:
    """Validate a repository-relative path before resolving or opening it."""

    try:
        relative = safe_relative_path(value)
        if not relative.parts:
            raise ValueError("path must not be empty")
        assert_public_path(Path(value))
        resolved = ReleaseRoot(root).resolve(relative.as_posix())
        assert_public_path(resolved)
    except (OSError, ValueError) as exc:
        raise ValueError(f"{label} has unsafe path: {value!r}") from exc
    return relative.as_posix(), resolved


def _load_frozen_digest_contract(root: Path) -> dict[str, dict[str, str]] | None:
    """Load the committed artifact digest contract after boundary checks."""

    _, manifest_path = _safe_repo_path(root, "FILE_MANIFEST.csv", "frozen manifest")
    _, checksum_path = _safe_repo_path(root, "CHECKSUMS.sha256", "frozen checksums")
    if not manifest_path.is_file() and not checksum_path.is_file():
        _, public_sources_path = _safe_repo_path(
            root, "data/public_sources.csv", "public source registry"
        )
        if public_sources_path.is_file():
            raise ValueError("frozen manifest/checksum files are required for a public full run")
        return None
    if not manifest_path.is_file() or not checksum_path.is_file():
        raise ValueError("frozen manifest/checksum files must be present together")

    manifest_payload = manifest_path.read_bytes()
    checksum_payload = checksum_path.read_bytes()
    if b"\r" in manifest_payload or b"\r" in checksum_payload:
        raise ValueError("frozen manifest/checksum files must use LF line endings")
    try:
        manifest_text = manifest_payload.decode("utf-8")
        checksum_text = checksum_payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("frozen manifest/checksum files must be UTF-8") from exc

    reader = csv.DictReader(manifest_text.splitlines())
    if tuple(reader.fieldnames or ()) != _FROZEN_MANIFEST_FIELDS:
        raise ValueError("frozen manifest has an invalid header")
    manifest: dict[str, str] = {}
    for line_number, row in enumerate(reader, start=2):
        if None in row or any(row.get(field) is None for field in _FROZEN_MANIFEST_FIELDS):
            raise ValueError(f"frozen manifest has a malformed row {line_number}")
        relative, _ = _safe_repo_path(
            root, row["path"].strip(), f"frozen manifest row {line_number}"
        )
        digest = row["sha256"].strip()
        if not _SHA256_RE.fullmatch(digest):
            raise ValueError(f"frozen manifest has an invalid digest at row {line_number}")
        if relative in manifest:
            raise ValueError(f"frozen manifest repeats path {relative!r}")
        manifest[relative] = digest

    checksums: dict[str, str] = {}
    for line_number, line in enumerate(checksum_text.splitlines(), start=1):
        match = _CHECKSUM_LINE.fullmatch(line)
        if not match:
            raise ValueError(f"frozen checksums has an invalid row {line_number}")
        digest, raw_relative = match.groups()
        relative, _ = _safe_repo_path(
            root, raw_relative, f"frozen checksum row {line_number}"
        )
        if relative in checksums:
            raise ValueError(f"frozen checksums repeats path {relative!r}")
        checksums[relative] = digest
    return {"manifest": manifest, "checksums": checksums}


def _validate_frozen_artifacts(
    contract: dict[str, dict[str, str]],
    artifacts: list[tuple[str, Path]],
) -> None:
    for relative, path in artifacts:
        actual = _sha256(path)
        expected_manifest = contract["manifest"].get(relative)
        expected_checksum = contract["checksums"].get(relative)
        if expected_manifest is None or expected_checksum is None:
            raise ValueError(
                f"frozen manifest/checksum digest missing for artifact {relative!r}"
            )
        if (
            expected_manifest != expected_checksum
            or actual != expected_manifest
        ):
            raise ValueError(
                f"frozen manifest/checksum digest mismatch for artifact {relative!r}"
            )


def _prepare_boundary(root: Path, output_root: Path) -> tuple[Path, Path]:
    """Validate root/output lexically before touching either location."""

    assert_public_path(Path(root))
    assert_public_path(Path(output_root))
    assert_public_path(Path(output_root) / "full_reproduction.json")
    resolved_root = Path(root).resolve(strict=False)
    resolved_root = resolve_public_path(resolved_root, resolved_root)
    resolved_output = Path(output_root).resolve()
    assert_public_path(resolved_root)
    assert_public_path(resolved_output)
    assert_public_path(resolved_output / "full_reproduction.json")
    if not resolved_root.is_dir():
        raise ValueError("release root is not a directory")
    if resolved_output == resolved_root or resolved_root in resolved_output.parents:
        raise ValueError("full reproduction output must be outside the release root")
    return resolved_root, resolved_output


def _option_values(
    tokens: list[str], option: str, output_id: str
) -> tuple[list[str], set[int]]:
    values: list[str] = []
    value_indices: set[int] = set()
    for index, argument in enumerate(tokens):
        if argument == option:
            if index + 1 >= len(tokens) or tokens[index + 1].startswith("--"):
                raise ValueError(
                    f"output {output_id!r} command has no value after {option}"
                )
            values.append(tokens[index + 1])
            value_indices.add(index + 1)
        elif argument.startswith(option + "="):
            raise ValueError(
                f"output {output_id!r} command must use {option} <path>"
            )
    return values, value_indices


def _log_relative_path(output_id: str) -> str:
    if not output_id or output_id in {".", ".."} or "/" in output_id or chr(92) in output_id:
        raise ValueError(f"output {output_id!r} has an unsafe log identifier")
    try:
        relative = safe_relative_path(f"logs/{output_id}.log")
        assert_public_path(Path(relative.as_posix()))
    except ValueError as exc:
        raise ValueError(f"output {output_id!r} has an unsafe log identifier") from exc
    return relative.as_posix()


def _validate_command(
    root: Path,
    row: dict[str, str],
    dataset_paths: dict[str, str],
) -> dict[str, Any]:
    output_id = row["output_id"]
    command = row["generation_command"]
    if any(character in command for character in _SHELL_METACHARACTERS):
        raise ValueError(f"output {output_id!r} command contains a shell metacharacter")
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as exc:
        raise ValueError(f"output {output_id!r} command is not parseable") from exc
    if len(tokens) < 2 or tokens[0] != "python":
        raise ValueError(
            f"output {output_id!r} command must begin with python scripts/<safe-relative .py>"
        )

    script_relative, script_path = _safe_repo_path(
        root, tokens[1], f"output {output_id!r} builder script"
    )
    script_parts = PurePosixPath(script_relative).parts
    if not script_parts or script_parts[0] != "scripts" or not script_relative.endswith(".py"):
        raise ValueError(
            f"output {output_id!r} builder script must be scripts/<safe-relative .py>"
        )

    output_values, output_value_indices = _option_values(tokens, "--output", output_id)
    if len(output_values) != 1:
        raise ValueError(f"output {output_id!r} command must have exactly one --output")
    expected_relative, expected_path = _safe_repo_path(
        root, row["expected_artifact"], f"output {output_id!r} expected artifact"
    )
    command_output_relative, _ = _safe_repo_path(
        root, output_values[0], f"output {output_id!r} --output"
    )
    if command_output_relative != expected_relative:
        raise ValueError(
            f"output {output_id!r} command output {command_output_relative!r} "
            f"does not match expected artifact {expected_relative!r}"
        )

    secondary_artifacts: list[dict[str, Any]] = []
    secondary_paths: set[str] = set()
    for secondary_value in row["secondary_artifacts"].split(";"):
        if not secondary_value:
            continue
        secondary_relative, secondary_path = _safe_repo_path(
            root,
            secondary_value,
            f"output {output_id!r} secondary artifact",
        )
        if secondary_relative in {expected_relative, *secondary_paths}:
            raise ValueError(
                f"output {output_id!r} repeats artifact {secondary_relative!r}"
            )
        secondary_paths.add(secondary_relative)
        secondary_artifacts.append(
            {"relative": secondary_relative, "path": secondary_path}
        )

    input_values, input_value_indices = _option_values(tokens, "--input", output_id)
    declared_ids = [item for item in row["input_dataset_ids"].split(";") if item]
    declared_inputs = [dataset_paths[dataset_id] for dataset_id in declared_ids]
    command_inputs = [
        _safe_repo_path(root, value, f"output {output_id!r} --input")[0]
        for value in input_values
    ]
    if sorted(command_inputs) != sorted(declared_inputs):
        raise ValueError(
            f"output {output_id!r} command inputs {command_inputs!r} "
            f"do not match registered inputs {declared_inputs!r}"
        )

    option_value_indices = output_value_indices | input_value_indices
    allowed_paths = set(declared_inputs) | {expected_relative, script_relative}
    for index, argument in enumerate(tokens):
        if index in option_value_indices or index == 0:
            continue
        if index == 1:
            continue
        if any(marker in argument for marker in ("..", ":", chr(92))) or argument.startswith(("/", "~")):
            raise ValueError(f"output {output_id!r} command contains an unsafe path")
        if "/" in argument:
            normalized, _ = _safe_repo_path(root, argument, f"output {output_id!r} command")
            if normalized not in allowed_paths:
                raise ValueError(
                    f"output {output_id!r} command contains an unregistered path {normalized!r}"
                )

    return {
        "output_id": output_id,
        "argv": [sys.executable, script_relative, *tokens[2:]],
        "script_relative": script_relative,
        "script_path": script_path,
        "artifact_relative": expected_relative,
        "artifact_path": expected_path,
        "secondary_artifacts": secondary_artifacts,
        "log_relative": _log_relative_path(output_id),
    }


def _write_log(path: Path, payload: dict[str, Any], root: Path, output_root: Path) -> None:
    assert_public_path(path)
    sanitized = {
        key: _redact_paths(value, root, output_root) if isinstance(value, str) else value
        for key, value in payload.items()
    }
    path.write_text(
        json.dumps(sanitized, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_report(output_root: Path, report: dict[str, Any]) -> None:
    report_path = output_root / "full_reproduction.json"
    assert_public_path(report_path)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _base_report() -> dict[str, Any]:
    return {
        "status": "FAIL",
        "mode": "full",
        "workflow_status": {
            "registry_validation": "not-run",
            "carrier_validation": "not-run",
            "manuscript_outputs": "not-run",
        },
        "executed_output_ids": [],
        "command_return_codes": {},
        "artifacts": {},
        "logs": {},
        "frozen_digest_checks": {"status": "not-run", "artifacts": 0},
        "error": None,
        "errors": [],
    }


def run_full(root: Path, output_root: Path) -> dict[str, object]:
    """Reproduce every registered output in deterministic registry order."""

    raw_root = Path(root)
    raw_output = Path(output_root)
    report: dict[str, Any] = _base_report()
    resolved_root: Path | None = None
    resolved_output: Path | None = None
    report_destination_ready = False
    try:
        resolved_root, resolved_output = _prepare_boundary(raw_root, raw_output)
        resolved_output.mkdir(parents=True, exist_ok=True)
        if not resolved_output.is_dir():
            raise ValueError("full reproduction output is not a directory")
        report_destination_ready = True
        registry_paths = {
            relative: _safe_repo_path(resolved_root, relative, "registry")[1]
            for relative in _REGISTRY_PATHS
        }
        registry_counts = validate_release_registry(resolved_root)
        datasets = load_dataset_registry(registry_paths[_REGISTRY_PATHS[0]])
        strict_output_ids = (
            _safe_repo_path(resolved_root, "data/public_sources.csv", "public source registry")[1]
            .is_file()
        )
        outputs = load_output_registry(
            registry_paths[_REGISTRY_PATHS[1]],
            enforce_fixed_ids=strict_output_ids,
        )
        frozen_digest_contract = _load_frozen_digest_contract(resolved_root)
        report["registry"] = dict(registry_counts)
        report["workflow_status"]["registry_validation"] = "reproduced"

        dataset_paths: dict[str, str] = {}
        dataset_files: dict[str, Path] = {}
        for row in datasets:
            relative, path = _safe_repo_path(
                resolved_root, row["public_path"], f"dataset {row['dataset_id']!r} public path"
            )
            dataset_paths[row["dataset_id"]] = relative
            dataset_files[row["dataset_id"]] = path
            if row["stage_action"] not in _CARRIER_ACTIONS:
                raise ValueError(
                    f"dataset {row['dataset_id']!r} has unsupported stage_action {row['stage_action']!r}"
                )

        jobs: list[dict[str, Any]] = []
        logs_dir = resolved_output / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_entries = [
            (row["output_id"], _log_relative_path(row["output_id"]))
            for row in outputs
        ]
        for output_id, log_relative in log_entries:
            report["logs"][output_id] = log_relative
            _write_log(
                resolved_output / Path(*log_relative.split("/")),
                {"output_id": output_id, "status": "NOT_RUN"},
                resolved_root,
                resolved_output,
            )
        for row in outputs:
            jobs.append(_validate_command(resolved_root, row, dataset_paths))

        for row in datasets:
            dataset_id = row["dataset_id"]
            path = dataset_files[dataset_id]
            declared = row["sha256"].strip()
            if not declared or not _SHA256_RE.fullmatch(declared):
                raise ValueError(f"dataset {dataset_id!r} must declare a SHA-256 carrier hash")
            if not path.is_file():
                raise ValueError(f"dataset {dataset_id!r} carrier is missing: {dataset_paths[dataset_id]}")
            actual = _sha256(path)
            if actual != declared:
                raise ValueError(
                    f"dataset {dataset_id!r} carrier sha256 mismatch for {dataset_paths[dataset_id]}"
                )
        report["workflow_status"]["carrier_validation"] = "reproduced"

        for job in jobs:
            if not job["script_path"].is_file():
                raise ValueError(
                    f"output {job['output_id']!r} builder script is missing: {job['script_relative']}"
                )

        environment = os.environ.copy()
        environment["PYTHONUTF8"] = "1"
        environment["MPLBACKEND"] = "Agg"
        for job in jobs:
            output_id = job["output_id"]
            try:
                completed = subprocess.run(
                    job["argv"],
                    cwd=resolved_root,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="strict",
                    env=environment,
                    shell=False,
                    check=False,
                )
            except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
                message = _redact_paths(exc, resolved_root, resolved_output)
                report["error"] = message
                report["errors"] = [message]
                _write_log(
                    resolved_output / Path(*job["log_relative"].split("/")),
                    {"output_id": output_id, "status": "FAIL", "error": message},
                    resolved_root,
                    resolved_output,
                )
                break

            report["executed_output_ids"].append(output_id)
            report["command_return_codes"][output_id] = completed.returncode
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            if completed.returncode != 0:
                message = f"output {output_id!r} failed with return code {completed.returncode}"
                if stderr.strip():
                    message += f": {_redact_paths(stderr.strip(), resolved_root, resolved_output)}"
                report["error"] = message
                report["errors"] = [message]
                _write_log(
                    resolved_output / Path(*job["log_relative"].split("/")),
                    {
                        "output_id": output_id,
                        "status": "FAIL",
                        "returncode": completed.returncode,
                        "stdout": stdout,
                        "stderr": stderr,
                    },
                    resolved_root,
                    resolved_output,
                )
                break

            artifact_paths = [
                (job["artifact_relative"], job["artifact_path"]),
                *[
                    (item["relative"], item["path"])
                    for item in job["secondary_artifacts"]
                ],
            ]
            missing_artifacts = [
                relative for relative, path in artifact_paths if not path.is_file()
            ]
            if missing_artifacts:
                message = (
                    f"output {output_id!r} expected artifact is missing: "
                    + ", ".join(missing_artifacts)
                )
                report["error"] = message
                report["errors"] = [message]
                _write_log(
                    resolved_output / Path(*job["log_relative"].split("/")),
                    {
                        "output_id": output_id,
                        "status": "FAIL",
                        "returncode": completed.returncode,
                        "stdout": stdout,
                        "stderr": stderr,
                        "error": message,
                    },
                    resolved_root,
                    resolved_output,
                )
                break

            if frozen_digest_contract is not None:
                _validate_frozen_artifacts(frozen_digest_contract, artifact_paths)
            primary_relative, primary_path = artifact_paths[0]
            report["artifacts"][output_id] = {
                "path": primary_relative,
                "sha256": _sha256(primary_path),
                "secondary_artifacts": [
                    {
                        "path": relative,
                        "sha256": _sha256(path),
                    }
                    for relative, path in artifact_paths[1:]
                ],
            }
            _write_log(
                resolved_output / Path(*job["log_relative"].split("/")),
                {
                    "output_id": output_id,
                    "status": "PASS",
                    "returncode": completed.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                },
                resolved_root,
                resolved_output,
            )
        else:
            report["status"] = "PASS"
            report["workflow_status"]["manuscript_outputs"] = "reproduced"
            if frozen_digest_contract is not None:
                report["frozen_digest_checks"] = {
                    "status": "PASS",
                    "artifacts": sum(
                        1
                        + len(job["secondary_artifacts"])
                        for job in jobs
                    ),
                }
    except (OSError, UnicodeError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        message = _redact_paths(
            exc,
            resolved_root or raw_root,
            resolved_output or raw_output,
        )
        report["error"] = message
        report["errors"] = [message]

    if report_destination_ready and resolved_output is not None:
        _write_report(resolved_output, report)
    return report


__all__ = ["run_full"]
