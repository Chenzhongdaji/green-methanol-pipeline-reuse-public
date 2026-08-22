"""Inventory loaders and fail-closed validation for the public release.

The inventories contain metadata and author-generated aggregates only.  They
do not provide a route to, or a copy of, restricted network files and other
third-party source payloads.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from pathlib import Path

from .contracts import ALLOWED_WORKFLOW_STATUSES, ReleaseRoot, safe_relative_path


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

CONTROLLED_FIELDS = (
    "dataset_id",
    "data_class",
    "share_status",
    "owner_or_provenance",
    "restriction_reason",
    "schema_summary",
    "access_route",
    "validation_substitute",
    "sha256",
    "hash_note",
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
    "src/green_methanol_pipeline_reuse.egg-info",
}

CONTROLLED_DATASET_IDS = {
    "city-topology-directed-network-v01",
    "facility-to-trunk-and-refinery-mapping-v01",
    "candidate-link-geometry-v01",
    "standard-map-gs2023-2767",
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_AUTHOR_SOURCE_TYPE = "author-generated aggregate"
_ENGINEERING_SOURCE_TYPE = "engineering source"


def _load_csv(path: Path, fields: tuple[str, ...], identifier: str) -> list[dict[str, str]]:
    """Load one UTF-8 CSV and reject schema or identifier violations."""

    path = Path(path)
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
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative_payload_files(root: Path) -> list[tuple[str, Path]]:
    """Return deterministic repository-relative payload files.

    The generated inventories are deliberately excluded.  Relative POSIX
    names are emitted regardless of the host platform so that the same tree
    produces byte-identical records on Windows and Linux.
    """

    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"release root is not a directory: {root}")
    payloads: list[tuple[str, Path]] = []
    excluded = {MANIFEST_FILENAME, CHECKSUMS_FILENAME}
    for path in root.rglob("*"):
        if not path.is_file() or path.name in excluded:
            continue
        relative_path = path.resolve().relative_to(root)
        relative = relative_path.as_posix()
        if any(
            relative == part
            or relative.startswith(part + "/")
            or part in relative_path.parts
            for part in _INVENTORY_SKIP_PARTS
        ):
            continue
        payloads.append((relative, path))
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


def _manifest_attributes(relative: str) -> tuple[str, str, str]:
    """Classify one payload path for the human-auditable manifest."""

    if relative in _CC_BY_CARRIERS:
        return "author-generated aggregate carrier", "CC BY 4.0", "author-generated aggregate data"
    if relative == "data/public_sources.csv":
        return "third-party provenance metadata", "metadata-only; third-party rights retained", "public-source metadata"
    if relative == "data/controlled_inputs_metadata.csv":
        return "restricted-input provenance metadata", "metadata-only; controlled rights retained", "controlled-input metadata"
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


def _render_manifest(root: Path, payloads: list[tuple[str, Path]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
    writer.writeheader()
    for relative, path in payloads:
        purpose, licence_scope, data_class = _manifest_attributes(relative)
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

    root = Path(root).resolve()
    payloads = _relative_payload_files(root)
    manifest_text = _render_manifest(root, payloads)
    manifest_path = root / MANIFEST_FILENAME
    manifest_path.write_text(manifest_text, encoding="utf-8", newline="\n")

    checksum_paths = sorted([relative for relative, _ in payloads] + [MANIFEST_FILENAME])
    checksum_rows = [
        f"{_sha256(root / Path(*relative.split('/')))}  {relative}"
        for relative in checksum_paths
    ]
    checksum_path = root / CHECKSUMS_FILENAME
    checksum_path.write_text("\n".join(checksum_rows) + "\n", encoding="utf-8", newline="\n")
    return {"manifest_rows": len(payloads), "checksum_rows": len(checksum_rows)}


def load_public_sources(path: Path) -> list[dict[str, str]]:
    """Load the public-source register using the exact release schema."""

    return _load_csv(Path(path), PUBLIC_SOURCE_FIELDS, "source_id")


def load_controlled_inputs(path: Path) -> list[dict[str, str]]:
    """Load the restricted-input metadata register using the exact schema."""

    return _load_csv(Path(path), CONTROLLED_FIELDS, "dataset_id")


def _claims_repository_cc_by(row: dict[str, str]) -> bool:
    rights = re.sub(r"[^a-z0-9]+", "", row["licence_or_rights_status"].casefold())
    return "ccby40" in rights


def _validate_controlled_rows(rows: list[dict[str, str]]) -> int:
    identifiers = {row["dataset_id"] for row in rows}
    if identifiers != CONTROLLED_DATASET_IDS:
        missing = sorted(CONTROLLED_DATASET_IDS - identifiers)
        extra = sorted(identifiers - CONTROLLED_DATASET_IDS)
        raise ValueError(f"controlled register IDs differ: missing={missing}, extra={extra}")

    zero_hash_rows = 0
    for row in rows:
        if row["share_status"].strip() != "metadata-only":
            raise ValueError(
                f"controlled input {row['dataset_id']!r} must have share_status=metadata-only"
            )
        for field in (
            "data_class",
            "owner_or_provenance",
            "restriction_reason",
            "schema_summary",
            "access_route",
            "validation_substitute",
        ):
            if not row[field].strip():
                raise ValueError(
                    f"controlled input {row['dataset_id']!r} requires non-empty {field}"
                )
        digest = row["sha256"].strip()
        hash_note = row["hash_note"].strip()
        if not digest:
            marker = "hash_unavailable:"
            if not hash_note.startswith(marker) or not hash_note[len(marker) :].strip():
                raise ValueError(
                    f"controlled input {row['dataset_id']!r} needs a hash_unavailable: marker and non-empty reason"
                )
            continue
        if set(digest) == {"0"}:
            zero_hash_rows += 1
            raise ValueError(f"all-zero hash is forbidden for {row['dataset_id']!r}")
        if not _SHA256_RE.fullmatch(digest):
            raise ValueError(
                f"sha256 for {row['dataset_id']!r} must be 64 lowercase hexadecimal characters"
            )
        if hash_note:
            raise ValueError(
                f"controlled input {row['dataset_id']!r} must leave hash_note empty when sha256 is present"
            )
    return zero_hash_rows


def validate_inventory(root: Path) -> dict[str, int]:
    """Validate both registers and return counts used by downstream tasks.

    Paths are resolved through Task 1's ``safe_relative_path``/``ReleaseRoot``
    contract, so callers cannot accidentally redirect validation outside the
    release tree.  ``ALLOWED_WORKFLOW_STATUSES`` is imported as the shared
    closed vocabulary for later workflow validators; inventory validation does
    not invent a second status vocabulary.
    """

    # Keep the path literals repository-relative and fail closed if Task 1's
    # path contract changes.  The status set is intentionally referenced here
    # so all workflow modules consume the same closed vocabulary.
    public_relative = safe_relative_path("data/public_sources.csv")
    controlled_relative = safe_relative_path("data/controlled_inputs_metadata.csv")
    if not ALLOWED_WORKFLOW_STATUSES:
        raise ValueError("workflow status vocabulary cannot be empty")
    release_root = ReleaseRoot(Path(root))
    public_path = release_root.resolve(str(public_relative))
    controlled_path = release_root.resolve(str(controlled_relative))

    public_rows = load_public_sources(public_path)
    controlled_rows = load_controlled_inputs(controlled_path)

    third_party_cc_by_rows = sum(
        1
        for row in public_rows
        if _claims_repository_cc_by(row)
        and row["source_type"] != _AUTHOR_SOURCE_TYPE
    )
    if third_party_cc_by_rows:
        raise ValueError("third-party source rows must not claim the repository CC BY licence")

    zero_hash_rows = _validate_controlled_rows(controlled_rows)
    return {
        "public_source_rows": len(public_rows),
        "engineering_source_rows": sum(
            row["source_type"].strip().lower() == _ENGINEERING_SOURCE_TYPE
            for row in public_rows
        ),
        "controlled_rows": len(controlled_rows),
        "zero_hash_rows": zero_hash_rows,
        "third_party_cc_by_rows": third_party_cc_by_rows,
    }


__all__ = [
    "CHECKSUMS_FILENAME",
    "CONTROLLED_DATASET_IDS",
    "CONTROLLED_FIELDS",
    "MANIFEST_FIELDS",
    "MANIFEST_FILENAME",
    "PUBLIC_SOURCE_FIELDS",
    "load_controlled_inputs",
    "load_public_sources",
    "validate_inventory",
    "write_release_inventories",
]
