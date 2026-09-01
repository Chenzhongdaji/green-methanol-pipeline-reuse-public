"""Repository-relative provenance validation for public carrier links."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any

from .contracts import safe_relative_path
from .safety import assert_public_path


SOURCE_MANIFEST = "data/raw/city_topology_v01/source_manifest.csv"
C3_UNLOCKING_COST = "data/processed/dynamic_analyses_v08/c3_unlocking_cost.csv"
SOURCE_MANIFEST_FIELDS = (
    "source_id",
    "dataset",
    "publisher",
    "source_url",
    "data_year",
    "accessed_on",
    "evidence_grade",
    "local_path",
    "origin_type",
    "parent_source_ids",
    "provenance_note",
    "sha256",
    "link_status",
    "repository_source_id",
)
PROVENANCE_STATUSES = {
    "external_only",
    "direct_public_carrier",
    "historical_metadata_only",
}
_SHA256_LENGTH = 64


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        return fields, list(reader)


def _registry_by_id(root: Path) -> dict[str, dict[str, str]]:
    path = root / "data" / "dataset_registry.csv"
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return {
            str(row.get("dataset_id", "")).strip(): {
                str(key): str(value or "").strip() for key, value in row.items()
            }
            for row in reader
            if row.get("dataset_id")
        }


def _relative_file(root: Path, value: str) -> Path | None:
    if not value or "://" in value or Path(value).is_absolute():
        return None
    try:
        relative = safe_relative_path(value)
        assert_public_path(Path(value))
    except ValueError:
        return None
    if not relative.parts:
        return None
    return root.joinpath(*relative.parts)


def _validate_source_manifest(root: Path) -> dict[str, Any]:
    path = root.joinpath(*SOURCE_MANIFEST.split("/"))
    result: dict[str, Any] = {
        "rows": 0,
        "direct_public_carrier_count": 0,
        "historical_metadata_only_count": 0,
        "external_only_count": 0,
        "unresolved_direct_links": [],
        "hash_mismatches": [],
        "errors": [],
    }
    if not path.is_file():
        result["errors"].append(f"missing provenance carrier: {SOURCE_MANIFEST}")
        return result
    try:
        fields, rows = _read_rows(path)
    except (OSError, UnicodeError, csv.Error) as exc:
        result["errors"].append(f"cannot read provenance carrier: {exc}")
        return result
    result["rows"] = len(rows)
    missing = sorted(set(SOURCE_MANIFEST_FIELDS) - set(fields))
    if missing:
        result["errors"].append(f"provenance carrier missing fields: {missing}")
        return result
    registry = _registry_by_id(root)
    seen: set[str] = set()
    for row in rows:
        source_id = str(row.get("source_id", "")).strip()
        status = str(row.get("link_status", "")).strip()
        if not source_id or source_id in seen:
            result["errors"].append(f"invalid or duplicate source_id: {source_id!r}")
            continue
        seen.add(source_id)
        if status not in PROVENANCE_STATUSES:
            result["errors"].append(f"invalid provenance link status for {source_id!r}: {status!r}")
            continue
        local_path = str(row.get("local_path", "")).strip()
        repository_source_id = str(row.get("repository_source_id", "")).strip()
        declared_hash = str(row.get("sha256", "")).strip()
        if status == "external_only":
            result["external_only_count"] += 1
            if not local_path.startswith("external://"):
                result["errors"].append(f"external source {source_id!r} must use external:// local_path")
            if declared_hash != "not_applicable":
                result["errors"].append(f"external source {source_id!r} must use not_applicable sha256")
            continue
        if status == "historical_metadata_only":
            result["historical_metadata_only_count"] += 1
            if not local_path.startswith("historical://"):
                result["errors"].append(
                    f"historical source {source_id!r} must use historical:// local_path"
                )
            if repository_source_id != "not_applicable":
                result["errors"].append(
                    f"historical source {source_id!r} must not claim a repository source ID"
                )
            if declared_hash != "not_applicable":
                result["errors"].append(
                    f"historical source {source_id!r} must use not_applicable sha256"
                )
            continue

        result["direct_public_carrier_count"] += 1
        target = _relative_file(root, local_path)
        registry_row = registry.get(repository_source_id)
        if target is None or not target.is_file():
            result["unresolved_direct_links"].append(source_id)
            continue
        if registry_row is None:
            result["errors"].append(
                f"direct source {source_id!r} references unknown repository source ID {repository_source_id!r}"
            )
        if registry_row and registry_row.get("public_path") != local_path:
            result["errors"].append(
                f"direct source {source_id!r} path does not match registry source {repository_source_id!r}"
            )
        try:
            actual_hash = _sha256(target)
        except OSError:
            result["unresolved_direct_links"].append(source_id)
            continue
        if len(declared_hash) != _SHA256_LENGTH or actual_hash != declared_hash:
            result["hash_mismatches"].append(source_id)
        if registry_row and registry_row.get("sha256") != declared_hash:
            result["hash_mismatches"].append(source_id)

    for key in ("unresolved_direct_links", "hash_mismatches", "errors"):
        result[key] = sorted(set(result[key]))
    return result


def _validate_c3_provenance(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"rows": 0, "errors": []}
    path = root.joinpath(*C3_UNLOCKING_COST.split("/"))
    if not path.is_file():
        # Minimal provenance fixtures may contain only the source manifest.
        # A full release is checked by the dataset registry/audit gate, so do
        # not manufacture a C3 failure for a deliberately smaller fixture.
        if (root / "data" / "dataset_registry.csv").is_file():
            result["errors"].append(f"missing C3 provenance carrier: {C3_UNLOCKING_COST}")
        return result
    try:
        fields, rows = _read_rows(path)
    except (OSError, UnicodeError, csv.Error) as exc:
        result["errors"].append(f"cannot read C3 provenance carrier: {exc}")
        return result
    result["rows"] = len(rows)
    required = {"flow_source", "flow_source_status"}
    missing = sorted(required - set(fields))
    if missing:
        result["errors"].append(f"C3 carrier missing provenance fields: {missing}")
        return result
    for row_number, row in enumerate(rows, start=2):
        source = str(row.get("flow_source", "")).strip()
        status = str(row.get("flow_source_status", "")).strip()
        if status == "historical_metadata_only":
            if not source.startswith("historical://"):
                result["errors"].append(f"C3 row {row_number} historical flow_source is not explicit")
        elif status == "direct_public_carrier":
            if not source.startswith("source-id:"):
                result["errors"].append(f"C3 row {row_number} direct flow_source is not a source ID")
        else:
            result["errors"].append(f"C3 row {row_number} has invalid flow_source_status {status!r}")
    result["errors"] = sorted(set(result["errors"]))
    return result


def validate_repository_provenance(root: Path) -> dict[str, Any]:
    """Validate repository-relative links and explicit historical boundaries."""

    root = Path(root).resolve()
    source_manifest = _validate_source_manifest(root)
    c3 = _validate_c3_provenance(root)
    errors = list(source_manifest["errors"]) + list(c3["errors"])
    errors.extend(
        f"unresolved direct provenance link: {source_id}"
        for source_id in source_manifest["unresolved_direct_links"]
    )
    errors.extend(
        f"provenance hash mismatch: {source_id}"
        for source_id in source_manifest["hash_mismatches"]
    )
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": sorted(set(errors)),
        "direct_public_carrier_count": source_manifest["direct_public_carrier_count"],
        "historical_metadata_only_count": source_manifest["historical_metadata_only_count"],
        "external_only_count": source_manifest["external_only_count"],
        "unresolved_direct_links": source_manifest["unresolved_direct_links"],
        "hash_mismatches": source_manifest["hash_mismatches"],
        "source_manifest_rows": source_manifest["rows"],
        "c3_rows": c3["rows"],
    }


__all__ = ["C3_UNLOCKING_COST", "SOURCE_MANIFEST", "validate_repository_provenance"]
