"""Inventory loaders and fail-closed validation for the public release.

The inventories contain metadata and author-generated aggregates only.  They
do not provide a route to, or a copy of, restricted network files and other
third-party source payloads.
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import shlex
from pathlib import Path

from .contracts import ReleaseRoot, safe_relative_path
from .safety import assert_public_path, resolve_public_path


PUBLIC_SOURCE_FIELDS = (
    "source_id",
    "title",
    "provider",
    "source_type",
    "stable_url_or_doi",
    "version_or_publication_date",
    "access_date",
    "used_for",
    "evidence_boundary",
    "redistribution_status",
    "licence_or_rights_status",
    "notes",
)

MANIFEST_FIELDS = (
    "path",
    "bytes",
    "sha256",
    "purpose",
    "licence_scope",
    "data_class",
)

MANIFEST_FILENAME = "FILE_MANIFEST.csv"
CHECKSUMS_FILENAME = "CHECKSUMS.sha256"

DATASET_REGISTRY_FIELDS = (
    "dataset_id",
    "public_path",
    "role",
    "origin",
    "access_route",
    "license",
    "sha256",
    "acquisition_command",
    "processing_command",
    "manuscript_uses",
    "source_relative_path",
    "stage_action",
)

OUTPUT_REGISTRY_FIELDS = (
    "output_id",
    "manuscript_location",
    "generation_command",
    "input_dataset_ids",
    "expected_artifact",
    "secondary_artifacts",
)

_DATASET_REQUIRED_FIELDS = tuple(
    field
    for field in DATASET_REGISTRY_FIELDS
    if field not in {
        "sha256",
        "acquisition_command",
        "processing_command",
        "source_relative_path",
    }
)
_OUTPUT_REQUIRED_FIELDS = tuple(
    field for field in OUTPUT_REGISTRY_FIELDS if field != "secondary_artifacts"
)
_FIGURE2E_FORBIDDEN_MARKERS = ("withheld", "status", "not_reproduced")
_COMMAND_INPUT_OPTION = "--input"
_COMMAND_OUTPUT_OPTION = "--output"
_NON_GENERATING_COMMANDS = {"cat", "echo", "printf", "type", "write-output"}
_INTERNAL_INPUT_PREFIXES = ("data/", "figures/source_data/")

# These paths are generated or environment-specific and therefore are not
# release payload.  Keep this rule identical to the audit closure contract;
# in particular, the manifest and checksum files are excluded from their own
# payload inventory to avoid a self-reference cycle.
_INVENTORY_SKIP_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".superpowers",
    "src/green_methanol_pipeline_reuse.egg-info",
}
_INVENTORY_SKIP_NAMES = frozenset(
    part.rsplit("/", 1)[-1] for part in _INVENTORY_SKIP_PARTS
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_AUTHOR_SOURCE_TYPE = "author-generated aggregate"
_ENGINEERING_SOURCE_TYPE = "engineering source"


def _resolve_standalone_path(path: Path) -> Path:
    """Resolve a direct file argument without changing relative-path meaning."""

    path = Path(path)
    root = Path.cwd() if not path.is_absolute() else path.parent
    return resolve_public_path(root, path)


def _load_csv(path: Path, fields: tuple[str, ...], identifier: str) -> list[dict[str, str]]:
    """Load one UTF-8 CSV and reject schema or identifier violations."""

    path = _resolve_standalone_path(Path(path))
    try:
        handle = path.open("r", encoding="utf-8", newline="")
    except OSError as exc:
        raise ValueError(f"cannot read inventory: {path}") from exc

    with handle:
        reader = csv.DictReader(handle)
        actual = reader.fieldnames
        if actual is None:
            raise ValueError(f"inventory has no header: {path}")
        if len(actual) != len(set(actual)) or any(not name for name in actual):
            raise ValueError(f"inventory has duplicate or blank columns: {path}")
        missing = [name for name in fields if name not in actual]
        extra = [name for name in actual if name not in fields]
        if missing or extra:
            details = []
            if missing:
                details.append(f"missing={missing}")
            if extra:
                details.append(f"extra={extra}")
            raise ValueError(f"invalid inventory columns ({', '.join(details)}): {path}")

        rows: list[dict[str, str]] = []
        seen: set[str] = set()
        for line_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"malformed inventory row {line_number}: {path}")
            normalized = {name: row[name] for name in fields}
            value = normalized[identifier].strip()
            if not value:
                raise ValueError(f"blank {identifier} at row {line_number}: {path}")
            if value in seen:
                raise ValueError(f"duplicate {identifier} {value!r}: {path}")
            seen.add(value)
            normalized[identifier] = value
            rows.append(normalized)
    return rows


def _sha256(path: Path) -> str:
    path = _resolve_standalone_path(Path(path))
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_registry_csv(
    path: Path,
    fields: tuple[str, ...],
    identifier: str,
) -> list[dict[str, str]]:
    """Load a registry with an exact header and normalized text fields."""

    path = _resolve_standalone_path(Path(path))
    try:
        handle = path.open("r", encoding="utf-8", newline="")
    except OSError as exc:
        raise ValueError(f"cannot read registry: {path}") from exc

    with handle:
        reader = csv.DictReader(handle)
        actual = tuple(reader.fieldnames or ())
        if actual != fields:
            raise ValueError(
                f"invalid registry columns: expected {list(fields)}, got {list(actual)}"
            )

        rows: list[dict[str, str]] = []
        seen: set[str] = set()
        for line_number, row in enumerate(reader, start=2):
            if not row or None in row or any(row.get(field) is None for field in fields):
                raise ValueError(f"malformed registry row {line_number}: {path}")
            normalized = {field: row[field].strip() for field in fields}
            value = normalized[identifier]
            if not value:
                raise ValueError(f"blank {identifier} at row {line_number}: {path}")
            if value in seen:
                raise ValueError(f"duplicate {identifier} {value!r}: {path}")
            seen.add(value)
            rows.append(normalized)
    return rows


def _normalize_registry_path(value: str, field: str, line_number: int) -> str:
    """Validate and normalize one repository-relative public path."""

    try:
        relative = safe_relative_path(value)
        if not relative.parts:
            raise ValueError("path must not be empty")
        # Task 1's guard is deliberately invoked separately from the lexical
        # relative-path contract so the exact excluded component remains a
        # fail-closed boundary for every registry path.
        assert_public_path(Path(value))
    except ValueError as exc:
        raise ValueError(f"invalid {field} path at row {line_number}: {value!r}") from exc
    return relative.as_posix()


def _validate_sha256(value: str, dataset_id: str, line_number: int) -> None:
    if value and not _SHA256_RE.fullmatch(value):
        raise ValueError(
            f"sha256 for dataset {dataset_id!r} at row {line_number} must be 64 lowercase hexadecimal characters"
        )


def _is_author_generated_deposited(row: dict[str, str]) -> bool:
    origin = row["origin"].casefold()
    route = row["access_route"].casefold()
    return "author-generated" in origin and (
        "repository" in route or "deposited" in route or "deposit" in route
    )


def _is_terminal_source_carrier(row: dict[str, str]) -> bool:
    role = row["role"].casefold()
    return "terminal" in role and "source" in role and "carrier" in role


def load_dataset_registry(path: Path) -> list[dict[str, str]]:
    """Load and validate the dataset-to-carrier registry."""

    rows = _load_registry_csv(Path(path), DATASET_REGISTRY_FIELDS, "dataset_id")
    for line_number, row in enumerate(rows, start=2):
        for field in _DATASET_REQUIRED_FIELDS:
            if not row[field]:
                raise ValueError(f"dataset {row['dataset_id']!r} missing {field} at row {line_number}")

        row["public_path"] = _normalize_registry_path(
            row["public_path"], "public_path", line_number
        )
        if row["source_relative_path"]:
            row["source_relative_path"] = _normalize_registry_path(
                row["source_relative_path"], "source_relative_path", line_number
            )
        _validate_sha256(row["sha256"], row["dataset_id"], line_number)

        if not row["acquisition_command"] and not _is_author_generated_deposited(row):
            raise ValueError(
                f"dataset {row['dataset_id']!r} requires acquisition_command unless author-generated and deposited"
            )
        if not row["processing_command"] and not _is_terminal_source_carrier(row):
            raise ValueError(
                f"dataset {row['dataset_id']!r} requires processing_command unless terminal source-data carrier"
            )
        if row["origin"].casefold().find("third-party") >= 0 and row["license"].casefold() == "cc by 4.0":
            raise ValueError(
                f"dataset {row['dataset_id']!r} cannot assign repository CC BY 4.0 to third-party data"
            )
    return rows


def _split_dataset_references(value: str, output_id: str, line_number: int) -> list[str]:
    references = [part.strip() for part in value.split(";")]
    if not value or any(not reference for reference in references):
        raise ValueError(
            f"output {output_id!r} requires a non-empty semicolon-delimited input_dataset_ids list at row {line_number}"
        )
    if len(references) != len(set(references)):
        raise ValueError(f"output {output_id!r} repeats an input dataset ID at row {line_number}")
    return references


def _split_secondary_artifacts(
    value: str, output_id: str, line_number: int
) -> list[str]:
    if not value.strip():
        return []
    references = [part.strip() for part in value.split(";")]
    if any(not reference for reference in references):
        raise ValueError(
            f"output {output_id!r} has a blank secondary artifact at row {line_number}"
        )
    if len(references) != len(set(references)):
        raise ValueError(
            f"output {output_id!r} repeats a secondary artifact at row {line_number}"
        )
    return [
        _normalize_registry_path(reference, "secondary_artifacts", line_number)
        for reference in references
    ]


def _validate_figure2e_contract(row: dict[str, str], line_number: int) -> None:
    output_id = row["output_id"]
    if output_id != "figure-02e":
        return
    command = row["generation_command"]
    command_casefold = command.casefold()
    if not command or any(marker in command_casefold for marker in _FIGURE2E_FORBIDDEN_MARKERS):
        raise ValueError(f"figure-02e requires a concrete generation command at row {line_number}")
    if "--output" not in command_casefold:
        raise ValueError(f"figure-02e generation command must target an output at row {line_number}")
    references = _split_dataset_references(row["input_dataset_ids"], output_id, line_number)
    if "figure-02-source-real" not in references:
        raise ValueError(
            "figure-02e must include figure-02-source-real as the carrier input"
        )
    if not row["expected_artifact"].endswith(".png"):
        raise ValueError(f"figure-02e expected_artifact must be a PNG target at row {line_number}")


def load_output_registry(path: Path) -> list[dict[str, str]]:
    """Load and validate the manuscript-output registry."""

    rows = _load_registry_csv(Path(path), OUTPUT_REGISTRY_FIELDS, "output_id")
    for line_number, row in enumerate(rows, start=2):
        _validate_figure2e_contract(row, line_number)
        for field in _OUTPUT_REQUIRED_FIELDS:
            if not row[field]:
                raise ValueError(f"output {row['output_id']!r} missing {field} at row {line_number}")
        row["input_dataset_ids"] = ";".join(
            _split_dataset_references(row["input_dataset_ids"], row["output_id"], line_number)
        )
        row["expected_artifact"] = _normalize_registry_path(
            row["expected_artifact"], "expected_artifact", line_number
        )
        secondary = _split_secondary_artifacts(
            row["secondary_artifacts"], row["output_id"], line_number
        )
        if row["output_id"] == "figure-02e" and secondary != [
            "figures/figure-02e.pdf"
        ]:
            raise ValueError(
                "figure-02e must declare figures/figure-02e.pdf as its secondary artifact"
            )
        if row["expected_artifact"] in secondary:
            raise ValueError(
                f"output {row['output_id']!r} repeats its primary artifact"
            )
        row["secondary_artifacts"] = ";".join(secondary)
    return rows


def _command_option_values(
    tokens: list[str], option: str, output_id: str, line_number: int
) -> tuple[list[str], set[int]]:
    values: list[str] = []
    value_indices: set[int] = set()
    for index, token in enumerate(tokens):
        if token == option:
            if index + 1 >= len(tokens) or tokens[index + 1].startswith("--"):
                raise ValueError(
                    f"output {output_id!r} generation_command has no value after {option} at row {line_number}"
                )
            values.append(tokens[index + 1])
            value_indices.add(index + 1)
        elif token.startswith(option + "="):
            raise ValueError(
                f"output {output_id!r} generation_command must use {option} <path> at row {line_number}"
            )
    return values, value_indices


def _normalize_command_path(value: str, output_id: str, option: str, line_number: int) -> str:
    try:
        relative = safe_relative_path(value)
        if not relative.parts:
            raise ValueError("path must not be empty")
        assert_public_path(Path(value))
    except ValueError as exc:
        raise ValueError(
            f"output {output_id!r} generation_command has an unsafe {option} path at row {line_number}"
        ) from exc
    return relative.as_posix()


def _validate_generation_command(
    row: dict[str, str],
    datasets_by_id: dict[str, dict[str, str]],
    line_number: int,
) -> None:
    output_id = row["output_id"]
    command = row["generation_command"]
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as exc:
        raise ValueError(
            f"output {output_id!r} generation_command is not parseable at row {line_number}"
        ) from exc
    if not tokens:
        raise ValueError(f"output {output_id!r} generation_command is empty at row {line_number}")
    executable = Path(tokens[0]).name.casefold()
    if executable in _NON_GENERATING_COMMANDS:
        raise ValueError(
            f"output {output_id!r} generation_command is not a generating command at row {line_number}"
        )

    output_values, output_value_indices = _command_option_values(
        tokens, _COMMAND_OUTPUT_OPTION, output_id, line_number
    )
    if len(output_values) != 1:
        raise ValueError(
            f"output {output_id!r} generation_command must have exactly one {_COMMAND_OUTPUT_OPTION} target at row {line_number}"
        )
    command_artifact = _normalize_command_path(
        output_values[0], output_id, _COMMAND_OUTPUT_OPTION, line_number
    )
    if command_artifact != row["expected_artifact"]:
        raise ValueError(
            f"output {output_id!r} generation_command target {command_artifact!r} does not match expected_artifact {row['expected_artifact']!r}"
        )

    input_values, input_value_indices = _command_option_values(
        tokens, _COMMAND_INPUT_OPTION, output_id, line_number
    )
    command_inputs = [
        _normalize_command_path(value, output_id, _COMMAND_INPUT_OPTION, line_number)
        for value in input_values
    ]
    declared_inputs = [
        datasets_by_id[dataset_id]["public_path"]
        for dataset_id in row["input_dataset_ids"].split(";")
    ]
    if sorted(command_inputs) != sorted(declared_inputs):
        raise ValueError(
            f"output {output_id!r} generation_command inputs {command_inputs!r} do not match declared dataset paths {declared_inputs!r}"
        )

    option_value_indices = output_value_indices | input_value_indices
    for index, token in enumerate(tokens):
        if index in option_value_indices:
            continue
        normalized_token = token.replace("\\", "/")
        if normalized_token.startswith(_INTERNAL_INPUT_PREFIXES):
            candidate = _normalize_command_path(
                normalized_token, output_id, "repository input", line_number
            )
            if candidate not in declared_inputs:
                raise ValueError(
                    f"output {output_id!r} generation_command contains undeclared repository input path {candidate!r}"
                )


def validate_release_registry(root: Path) -> dict[str, int]:
    """Validate registry schemas and output-to-dataset referential integrity."""

    release_root = ReleaseRoot(Path(root))
    datasets = load_dataset_registry(
        release_root.resolve("data/dataset_registry.csv")
    )
    outputs = load_output_registry(
        release_root.resolve("data/output_registry.csv")
    )

    dataset_ids = {row["dataset_id"] for row in datasets}
    datasets_by_id = {row["dataset_id"]: row for row in datasets}
    referenced: set[str] = set()
    artifacts: set[str] = set()
    for line_number, row in enumerate(outputs, start=2):
        output_id = row["output_id"]
        references = row["input_dataset_ids"].split(";")
        missing = sorted(set(references) - dataset_ids)
        if missing:
            raise ValueError(
                f"output {output_id!r} references undeclared dataset(s): {', '.join(missing)}"
            )
        _validate_generation_command(row, datasets_by_id, line_number)
        referenced.update(references)
        artifact = row["expected_artifact"]
        if artifact in artifacts:
            raise ValueError(f"duplicate expected_artifact {artifact!r}")
        artifacts.add(artifact)
        for secondary in row["secondary_artifacts"].split(";"):
            if not secondary:
                continue
            if secondary in artifacts:
                raise ValueError(f"duplicate expected_artifact {secondary!r}")
            artifacts.add(secondary)

    return {
        "datasets": len(datasets),
        "outputs": len(outputs),
        "referenced_datasets": len(referenced),
    }


def _relative_payload_files(root: Path) -> list[tuple[str, Path]]:
    """Return deterministic repository-relative payload files.

    The generated inventories are deliberately excluded.  Relative POSIX
    names are emitted regardless of the host platform so that the same tree
    produces byte-identical records on Windows and Linux.
    """

    root = Path(root).resolve(strict=False)
    root = resolve_public_path(root, root)
    if not root.is_dir():
        raise ValueError(f"release root is not a directory: {root}")
    assert_public_path(root)
    payloads: list[tuple[str, Path]] = []
    excluded = {MANIFEST_FILENAME, CHECKSUMS_FILENAME}
    # ``Path.rglob`` cannot prune a directory before descending into it.  Walk
    # top-down and apply the path guard to directory entries before they are
    # opened, so the excluded directory is never traversed or hashed.
    def onerror(exc: OSError) -> None:
        raise ValueError(f"payload walk failed: {exc}") from exc

    for directory, dirnames, filenames in os.walk(root, topdown=True, onerror=onerror):
        directory_path = Path(directory)
        kept_dirnames: list[str] = []
        for name in sorted(dirnames):
            if name in _INVENTORY_SKIP_NAMES:
                continue
            candidate = directory_path / name
            resolve_public_path(root, candidate)
            kept_dirnames.append(name)
        dirnames[:] = kept_dirnames
        for name in sorted(filenames):
            if name in excluded or name in _INVENTORY_SKIP_NAMES:
                continue
            path = directory_path / name
            try:
                resolved_path = resolve_public_path(root, path)
                relative_path = resolved_path.relative_to(root)
            except (OSError, ValueError) as exc:
                raise ValueError(f"unsafe release payload path: {path}") from exc
            payloads.append((relative_path.as_posix(), resolved_path))
    return sorted(payloads, key=lambda item: item[0])


_CC_BY_CARRIERS = frozenset(
    {
        "data/author_derived/figure2_aggregate_source.csv",
        "data/author_derived/terminal_gap_aggregate.csv",
        "figures/source_data/figure-01.csv",
        "figures/source_data/figure-03.csv",
        "figures/source_data/figure-04.csv",
        "figures/source_data/figure-05.csv",
        "figures/panel_map.csv",
        "qa/expected/headline_claims.csv",
    }
)


def _registry_manifest_attributes(
    root: Path,
) -> tuple[dict[str, tuple[str, str, str]], dict[str, tuple[str, str, str]]]:
    """Load manifest classifications from the authoritative registries."""

    dataset_path = resolve_public_path(root, root / "data" / "dataset_registry.csv")
    output_path = resolve_public_path(root, root / "data" / "output_registry.csv")
    dataset_attributes: dict[str, tuple[str, str, str]] = {}
    output_attributes: dict[str, tuple[str, str, str]] = {}
    if dataset_path.is_file():
        for row in load_dataset_registry(dataset_path):
            public_path = row["public_path"]
            attributes = (row["role"], row["license"], row["origin"])
            if public_path in dataset_attributes and dataset_attributes[public_path] != attributes:
                raise ValueError(f"dataset registry maps one path to conflicting attributes: {public_path}")
            dataset_attributes[public_path] = attributes
    if output_path.is_file():
        for row in load_output_registry(output_path):
            attributes = (
                f"manuscript output: {row['manuscript_location']}",
                "generated artifact; see registered inputs",
                "manuscript output",
            )
            for artifact in (
                [row["expected_artifact"]]
                + [item for item in row["secondary_artifacts"].split(";") if item]
            ):
                if artifact in output_attributes and output_attributes[artifact] != attributes:
                    raise ValueError(f"output registry maps one artifact to conflicting attributes: {artifact}")
                output_attributes[artifact] = attributes
    return dataset_attributes, output_attributes


def _manifest_attributes(
    relative: str,
    dataset_attributes: dict[str, tuple[str, str, str]] | None = None,
    output_attributes: dict[str, tuple[str, str, str]] | None = None,
) -> tuple[str, str, str]:
    """Classify one payload path for the human-auditable manifest."""

    if dataset_attributes and relative in dataset_attributes:
        return dataset_attributes[relative]
    if output_attributes and relative in output_attributes:
        return output_attributes[relative]
    if relative in _CC_BY_CARRIERS:
        return "author-generated aggregate carrier", "CC BY 4.0", "author-generated aggregate data"
    if relative == "data/public_sources.csv":
        return "third-party provenance metadata", "metadata-only; third-party rights retained", "public-source metadata"
    if relative.startswith("data/dictionaries/"):
        return "field dictionary and boundary metadata", "MIT", "documentation"
    if relative.startswith("data/"):
        return "reviewed release data or metadata", "MIT", "release metadata"
    if relative.startswith("figures/"):
        return "figure carrier metadata or aggregate source", "MIT", "figure metadata"
    if relative.startswith("qa/"):
        return "verification fixture and expected result", "MIT", "verification data"
    if relative.startswith("tests/"):
        return "automated verification code", "MIT", "test code"
    if relative.startswith("src/") or relative.startswith("scripts/"):
        return "release workflow code", "MIT", "code"
    if relative.startswith("environment/") or relative.startswith(".github/"):
        return "runtime or continuous-integration configuration", "MIT", "configuration"
    if relative == "LICENSE":
        return "software licence boundary", "MIT", "licence text"
    if relative == "LICENSE-DATA":
        return "author-generated aggregate data licence boundary", "CC BY 4.0 terms", "licence text"
    return "release documentation or metadata", "MIT", "documentation"


def _render_manifest(
    root: Path,
    payloads: list[tuple[str, Path]],
    dataset_attributes: dict[str, tuple[str, str, str]] | None = None,
    output_attributes: dict[str, tuple[str, str, str]] | None = None,
) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
    writer.writeheader()
    for relative, path in payloads:
        purpose, licence_scope, data_class = _manifest_attributes(
            relative, dataset_attributes, output_attributes
        )
        writer.writerow(
            {
                "path": relative,
                "bytes": str(path.stat().st_size),
                "sha256": _sha256(path),
                "purpose": purpose,
                "licence_scope": licence_scope,
                "data_class": data_class,
            }
        )
    return output.getvalue()


def write_release_inventories(root: Path) -> dict[str, int]:
    """Write deterministic ``FILE_MANIFEST.csv`` and ``CHECKSUMS.sha256``.

    The manifest covers every release payload except both generated inventory
    files.  The checksum file covers the same payload plus the manifest itself,
    but never itself; this explicit exclusion makes regeneration deterministic
    and avoids an impossible checksum cycle.
    """

    root = Path(root).resolve(strict=False)
    root = resolve_public_path(root, root)
    assert_public_path(root)
    payloads = _relative_payload_files(root)
    dataset_attributes, output_attributes = _registry_manifest_attributes(root)
    manifest_text = _render_manifest(
        root, payloads, dataset_attributes, output_attributes
    )
    manifest_path = resolve_public_path(root, root / MANIFEST_FILENAME)
    manifest_path.write_text(manifest_text, encoding="utf-8", newline="\n")

    checksum_paths = sorted([relative for relative, _ in payloads] + [MANIFEST_FILENAME])
    checksum_rows = []
    for relative in checksum_paths:
        path = resolve_public_path(root, root / Path(*relative.split("/")))
        checksum_rows.append(f"{_sha256(path)}  {relative}")
    checksum_path = resolve_public_path(root, root / CHECKSUMS_FILENAME)
    checksum_path.write_text("\n".join(checksum_rows) + "\n", encoding="utf-8", newline="\n")
    return {"manifest_rows": len(payloads), "checksum_rows": len(checksum_rows)}


def load_public_sources(path: Path) -> list[dict[str, str]]:
    """Load the public-source register using the exact release schema."""

    return _load_csv(Path(path), PUBLIC_SOURCE_FIELDS, "source_id")


def _claims_repository_cc_by(row: dict[str, str]) -> bool:
    rights = re.sub(r"[^a-z0-9]+", "", row["licence_or_rights_status"].casefold())
    return "ccby40" in rights


def validate_inventory(root: Path) -> dict[str, int]:
    """Validate the public source and dataset/output registries."""

    release_root = ReleaseRoot(Path(root))
    public_path = release_root.resolve("data/public_sources.csv")

    public_rows = load_public_sources(public_path)
    registry_counts = validate_release_registry(Path(root))

    third_party_cc_by_rows = sum(
        1
        for row in public_rows
        if _claims_repository_cc_by(row)
        and row["source_type"] != _AUTHOR_SOURCE_TYPE
    )
    if third_party_cc_by_rows:
        raise ValueError("third-party source rows must not claim the repository CC BY licence")

    return {
        "public_source_rows": len(public_rows),
        "engineering_source_rows": sum(
            row["source_type"].strip().lower() == _ENGINEERING_SOURCE_TYPE
            for row in public_rows
        ),
        "third_party_cc_by_rows": third_party_cc_by_rows,
        "dataset_rows": registry_counts["datasets"],
        "output_rows": registry_counts["outputs"],
        "referenced_dataset_rows": registry_counts["referenced_datasets"],
    }


__all__ = [
    "CHECKSUMS_FILENAME",
    "DATASET_REGISTRY_FIELDS",
    "MANIFEST_FIELDS",
    "MANIFEST_FILENAME",
    "OUTPUT_REGISTRY_FIELDS",
    "PUBLIC_SOURCE_FIELDS",
    "load_dataset_registry",
    "load_output_registry",
    "load_public_sources",
    "validate_release_registry",
    "validate_inventory",
    "write_release_inventories",
]
