"""Fail-closed audit gates for the public release.

The audit deliberately treats the repository as a publication payload.  It
checks metadata, inventories, aggregate reproduction, disclosure patterns and
(when present) the two-level manifest closure.  Reports are returned as plain
JSON-compatible dictionaries so the CLI can write them outside the immutable
tree.
"""

from __future__ import annotations

import csv
import hashlib
import re
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .contracts import ReleaseRoot, safe_relative_path
from .inventory import CONTROLLED_DATASET_IDS, validate_inventory
from .reproduce import run_reproduction


_MANIFEST_FIELDS = ("path", "bytes", "sha256", "purpose", "licence_scope", "data_class")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ZERO_HASH_RE = re.compile(r"(?<![0-9a-f])[0]{64}(?![0-9a-f])")
_CHECKSUM_LINE_RE = re.compile(r"^([0-9a-f]{64})  ([^\r\n]+)$")

# Only high-confidence credential forms are used.  The fragments are assembled
# so the scanner's own source does not contain a copyable token-looking value.
_TOKEN_PREFIXES = ("gh" + "p_", "github" + "_pat_", "sk-")
_TOKEN_RE = re.compile(
    r"(?:" + "|".join(re.escape(prefix) for prefix in _TOKEN_PREFIXES) + r")[A-Za-z0-9_\-]{20,}"
)
_AWS_KEY_RE = re.compile(r"(?<![A-Z0-9])AKIA[A-Z0-9]{16}(?![A-Z0-9])")
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_CREDENTIAL_URL_RE = re.compile(r"https?://[^\s/@:]+:[^\s/@]+@")

# A drive-letter path is bounded so ordinary URLs such as https:// do not
# match the single letter immediately before their colon.  POSIX home names
# are assembled from components for the same reason: the audit itself is not a
# leaked path fixture.
_DRIVE_PATH_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/](?![\\/])")
_UNC_PATH_RE = re.compile(r"(?<![A-Za-z])\\\\[^\\/\s]+[\\/][^\\/\s]+")
_POSIX_HOME_RE = re.compile(r"(?<![A-Za-z0-9])/(?:home|Users|root)/")

# Restricted payloads are detected only in payload-like data files and names.
# Metadata may legitimately mention the controlled dataset family IDs without
# redistributing the files; an extension or restricted schema field indicates
# an actual carrier leak.
_RESTRICTED_NAME_RE = re.compile(
    r"(?i)(?:pipeline[_-]?network[_-]?segments|edge[_-]?flows|facility[_-]?to[_-]?(?:trunk|refinery)|"
    r"refinery[_-]?to[_-]?pipeline[_-]?node[_-]?assignment|candidate[_-].*(?:link|links|geometry|geometries)|"
    r"airport[_-]?to[_-]?refinery[_-]?assignment|full[_-]?airport[_-]?demand[_-]?nodes|"
    r"physical[_-]?(?:edges|nodes)|standard[_-]?map[_-]?gs[_-]?2023[_-]?2767|"
    r"gs[_-]?2023[_-]?2767)(?:[_-][a-z0-9]+)*\.(?:csv|tsv|json|graphml|geojson|gpkg|shp|jpg|eps)$"
)
_RESTRICTED_SCHEMA_FIELDS = {
    "candidate_id",
    "candidate_ids",
    "from_lon",
    "from_lat",
    "to_lon",
    "to_lat",
    "node_id",
    "node_ids",
    "edge_id",
    "edge_ids",
    "pipeline_node_id",
    "refinery_node_id",
}

_TEXT_SUFFIXES = {
    ".c",
    ".cff",
    ".cfg",
    ".csv",
    ".gitattributes",
    ".gitignore",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".rst",
    ".sha256",
    ".toml",
    ".tsv",
    ".txt",
    ".xml",
    ".yml",
    ".yaml",
}
_TEXT_NAMES = {".gitattributes", ".gitignore", "LICENSE", "LICENSE-DATA"}
_SKIP_PARTS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    "qa/external",
    "qa/reports",
    "external_qa",
}

_REQUIRED_METADATA = (
    "README.md",
    "DATA_AVAILABILITY.md",
    "CODE_AVAILABILITY.md",
    "MANUSCRIPT_SCOPE.md",
    "CITATION.cff",
    "NOTICE.md",
    "LICENSE",
    "LICENSE-DATA",
    "environment/requirements.txt",
    "environment/environment.md",
    ".github/workflows/ci.yml",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _is_skipped(path: Path, root: Path) -> bool:
    relative = _relative(root, path)
    return any(
        relative == part or relative.startswith(part + "/") or part in path.parts
        for part in _SKIP_PARTS
    )


def _iter_payload_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_file() and not _is_skipped(path, root):
            yield path


def _text_payload(path: Path) -> str | None:
    """Decode a text-like payload; return None for opaque binary files."""

    if path.suffix.casefold() not in _TEXT_SUFFIXES and path.name not in _TEXT_NAMES:
        return None
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return None


def _docx_xml_payload(path: Path) -> Iterable[tuple[str, str]]:
    if path.suffix.casefold() != ".docx":
        return
    try:
        with zipfile.ZipFile(path) as package:
            for name in sorted(package.namelist()):
                if name.casefold().endswith(".xml"):
                    try:
                        yield f"{path.name}!{name}", package.read(name).decode("utf-8")
                    except (KeyError, UnicodeDecodeError, zipfile.BadZipFile):
                        continue
    except (OSError, zipfile.BadZipFile):
        return


def _scan_disclosures(root: Path) -> dict[str, Any]:
    absolute: list[str] = []
    credentials: list[str] = []
    restricted: list[str] = []
    zero_hashes: list[str] = []
    lf_hits: list[str] = []
    utf8_hits: list[str] = []
    size_hits: list[str] = []
    exclusions: list[str] = []

    def inspect(label: str, text: str, *, payload_schema: bool = False) -> None:
        if "\r" in text:
            lf_hits.append(label)
        for pattern in (_DRIVE_PATH_RE, _UNC_PATH_RE, _POSIX_HOME_RE):
            if pattern.search(text):
                absolute.append(label)
                break
        if any(pattern.search(text) for pattern in (_TOKEN_RE, _AWS_KEY_RE, _PRIVATE_KEY_RE, _CREDENTIAL_URL_RE)):
            credentials.append(label)
        if _ZERO_HASH_RE.search(text):
            zero_hashes.append(label)
        if payload_schema:
            try:
                fieldnames = next(csv.reader(text.splitlines()))
            except (StopIteration, csv.Error):
                fieldnames = []
            forbidden = sorted({field.casefold() for field in fieldnames} & _RESTRICTED_SCHEMA_FIELDS)
            if forbidden:
                restricted.append(f"{label}:schema={','.join(forbidden)}")
            if _RESTRICTED_NAME_RE.search(text):
                restricted.append(label)

    for path in _iter_payload_files(root):
        relative = _relative(root, path)
        if path.stat().st_size >= 100 * 1024 * 1024:
            size_hits.append(relative)
        if _RESTRICTED_NAME_RE.search(path.name):
            restricted.append(f"{relative}:filename")
        text = _text_payload(path)
        if text is None:
            if path.suffix.casefold() in _TEXT_SUFFIXES or path.name in _TEXT_NAMES:
                utf8_hits.append(relative)
            continue
        inspect(relative, text, payload_schema=path.suffix.casefold() in {".csv", ".tsv", ".json"})

    for path in _iter_payload_files(root):
        if path.suffix.casefold() != ".docx":
            continue
        for label, text in _docx_xml_payload(path):
            inspect(label, text)

    return {
        "absolute_path_hits": sorted(set(absolute)),
        "credential_hits": sorted(set(credentials)),
        "restricted_payload_hits": sorted(set(restricted)),
        "zero_hash_hits": sorted(set(zero_hashes)),
        "lf_hits": sorted(set(lf_hits)),
        "utf8_hits": sorted(set(utf8_hits)),
        "size_hits": sorted(set(size_hits)),
        "scan_exclusions": exclusions,
    }


def _check_required_metadata(root: Path) -> list[str]:
    return [relative for relative in _REQUIRED_METADATA if not _resolve(root, relative).is_file()]


def _resolve(root: Path, relative: str) -> Path:
    return ReleaseRoot(Path(root)).resolve(relative)


def _read_text(root: Path, relative: str) -> str:
    path = _resolve(root, relative)
    return path.read_text(encoding="utf-8")


def _validate_metadata(root: Path) -> list[str]:
    errors: list[str] = []
    missing = _check_required_metadata(root)
    errors.extend(f"missing metadata: {item}" for item in missing)
    if missing:
        return errors

    readme = _read_text(root, "README.md")
    heading_positions = [
        readme.find("What this release reproduces"),
        readme.find("What this release does not reproduce"),
    ]
    if heading_positions[0] < 0 or heading_positions[1] < 0 or heading_positions[0] > heading_positions[1]:
        errors.append("README must lead with the reproduction and non-reproduction boundaries")
    if "Level 1" not in readme or "Level 2" not in readme:
        errors.append("README must state Level 1 and Level 2")
    data = _read_text(root, "DATA_AVAILABILITY.md")
    code = _read_text(root, "CODE_AVAILABILITY.md")
    if "Data Availability" not in data or "Code Availability" in data:
        errors.append("DATA_AVAILABILITY.md must be a separate data statement")
    if "Code Availability" not in code or "Data Availability" in code:
        errors.append("CODE_AVAILABILITY.md must be a separate code statement")
    for relative in ("README.md", "DATA_AVAILABILITY.md", "CODE_AVAILABILITY.md"):
        if "10.5281/zenodo" in _read_text(root, relative).casefold() or "doi:" in _read_text(root, relative).casefold():
            errors.append(f"{relative} must not claim a DOI")

    scope = _read_text(root, "MANUSCRIPT_SCOPE.md")
    if "green_methanol_pipeline_reuse_v1.21_en.docx" not in scope:
        errors.append("MANUSCRIPT_SCOPE.md must record the authority filename")
    if "d6c9cec04888efdcd125ef946edad139990e81fb630afc11c7fe94bb2cca4f6a" not in scope:
        errors.append("MANUSCRIPT_SCOPE.md must record the authority SHA-256")
    if any(pattern.search(scope) for pattern in (_DRIVE_PATH_RE, _UNC_PATH_RE, _POSIX_HOME_RE)):
        errors.append("MANUSCRIPT_SCOPE.md must not include a local path")

    cff = _read_text(root, "CITATION.cff")
    required_cff = (
        "Green methanol pipeline reuse: public data and code release",
        "version: 1.0.0",
        "https://github.com/Chenzhongdaji/green-methanol-pipeline-reuse",
        "date-released: 2026-08-14",
        "name: Research team",
    )
    for marker in required_cff:
        if marker not in cff:
            errors.append(f"CITATION.cff missing required metadata: {marker}")
    if re.search(r"(?im)^\s*(?:-\s*)?(?:orcid|family-names|given-names):", cff):
        errors.append("CITATION.cff must not invent personal or ORCID metadata")
    if "repository: " in cff and "https://github.com/Chenzhongdaji/green-methanol-pipeline-reuse" not in cff:
        errors.append("CITATION.cff repository URL differs from the release remote")

    license_text = _read_text(root, "LICENSE")
    if "MIT License" not in license_text or "Permission is hereby granted, free of charge" not in license_text:
        errors.append("LICENSE must contain the complete MIT notice")
    data_license = _read_text(root, "LICENSE-DATA")
    if "Creative Commons Attribution 4.0 International" not in data_license or "creativecommons.org/licenses/by/4.0/" not in data_license:
        errors.append("LICENSE-DATA must state CC BY 4.0 and its official reference")
    notice = _read_text(root, "NOTICE.md")
    if "third-party" not in notice.casefold() or "controlled" not in notice.casefold():
        errors.append("NOTICE.md must exclude third-party and controlled materials")

    requirements = _read_text(root, "environment/requirements.txt").splitlines()
    requirement_lines = [line.strip() for line in requirements if line.strip() and not line.lstrip().startswith("#")]
    if "pandas==3.0.1" not in requirement_lines or "pytest==8.4.2" not in requirement_lines:
        errors.append("environment requirements must pin pandas==3.0.1 and pytest==8.4.2")
    return errors


def _check_licence_scope(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        stats = validate_inventory(root)
    except (OSError, ValueError) as exc:
        errors.append(f"inventory validation failed: {exc}")
        return errors
    if stats["third_party_cc_by_rows"]:
        errors.append("third-party inventory rows claim CC BY")
    aggregate_files = (
        "data/dictionaries/figure_01.md",
        "data/dictionaries/figure_03.md",
        "data/dictionaries/figure_04.md",
        "data/dictionaries/figure_05.md",
        "data/dictionaries/headline_claims.md",
        "data/dictionaries/panel_map.md",
        "data/dictionaries/terminal_gap_aggregate.md",
    )
    for relative in aggregate_files:
        try:
            text = _read_text(root, relative)
        except (OSError, ValueError):
            continue
        if "author-generated aggregate data" not in text:
            errors.append(f"{relative} must label the CC BY aggregate scope")
    for relative in ("data/dictionaries/public_sources.md", "data/dictionaries/controlled_inputs.md"):
        try:
            if "author-generated aggregate data" in _read_text(root, relative):
                errors.append(f"{relative} must not grant CC BY to metadata")
        except (OSError, ValueError):
            pass
    return errors


def _payload_files_for_manifest(root: Path) -> set[str]:
    excluded = {"FILE_MANIFEST.csv", "CHECKSUMS.sha256"}
    return {
        _relative(root, path)
        for path in _iter_payload_files(root)
        if _relative(root, path) not in excluded
    }


def _read_manifest(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    try:
        payload = path.read_bytes()
    except OSError as exc:
        return [], [str(exc)]
    if b"\r" in payload:
        errors.append("FILE_MANIFEST.csv must use LF line endings")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return [], ["FILE_MANIFEST.csv is not UTF-8"]
    reader = csv.DictReader(text.splitlines())
    if tuple(reader.fieldnames or ()) != _MANIFEST_FIELDS:
        return [], ["FILE_MANIFEST.csv has an invalid header"]
    rows: list[dict[str, str]] = []
    for line_number, row in enumerate(reader, start=2):
        if None in row or any(value is None for value in row.values()):
            errors.append(f"invalid manifest row {line_number}")
            continue
        normalized = {field: row[field].strip() for field in _MANIFEST_FIELDS}
        try:
            safe_relative_path(normalized["path"])
        except ValueError:
            errors.append(f"unsafe manifest path at row {line_number}")
        if not normalized["path"] or not _SHA256_RE.fullmatch(normalized["sha256"]):
            errors.append(f"invalid manifest digest/path at row {line_number}")
        try:
            byte_count = int(normalized["bytes"])
        except ValueError:
            errors.append(f"invalid manifest byte count at row {line_number}")
        else:
            if byte_count < 0:
                errors.append(f"invalid manifest byte count at row {line_number}")
        for field in ("purpose", "licence_scope", "data_class"):
            if not normalized[field]:
                errors.append(f"blank manifest {field} at row {line_number}")
        rows.append(normalized)
    return rows, errors


def _read_checksums(path: Path) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    try:
        payload = path.read_bytes()
    except OSError as exc:
        return {}, [str(exc)]
    if b"\r" in payload:
        errors.append("CHECKSUMS.sha256 must use LF line endings")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return {}, ["CHECKSUMS.sha256 is not UTF-8"]
    values: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = _CHECKSUM_LINE_RE.fullmatch(line)
        if not match:
            errors.append(f"invalid checksum row {line_number}")
            continue
        digest, relative = match.groups()
        try:
            safe_relative_path(relative)
        except ValueError:
            errors.append(f"unsafe checksum path at row {line_number}")
            continue
        if relative in values:
            errors.append(f"duplicate checksum path at row {line_number}")
        values[relative] = digest
    return values, errors


def verify_manifest_closure(root: Path) -> dict[str, object]:
    """Verify one-to-one manifest/checksum closure over the release payload."""

    root = Path(root).resolve()
    manifest_path = root / "FILE_MANIFEST.csv"
    checksum_path = root / "CHECKSUMS.sha256"
    result: dict[str, object] = {
        "manifest_present": manifest_path.is_file(),
        "checksums_present": checksum_path.is_file(),
        "orphan_files": [],
        "missing_files": [],
        "hash_mismatches": [],
        "checksum_orphan_files": [],
        "checksum_missing_files": [],
        "checksum_hash_mismatches": [],
        "errors": [],
    }
    errors: list[str] = []
    if not manifest_path.is_file() or not checksum_path.is_file():
        errors.append("manifest and checksum files are required")
        result["errors"] = errors
        result["status"] = "FAIL"
        return result
    rows, manifest_errors = _read_manifest(manifest_path)
    checksums, checksum_errors = _read_checksums(checksum_path)
    errors.extend(manifest_errors)
    errors.extend(checksum_errors)
    manifest_paths = [row["path"] for row in rows]
    if len(manifest_paths) != len(set(manifest_paths)):
        errors.append("manifest paths must be unique")
    payload_paths = _payload_files_for_manifest(root)
    manifest_set = set(manifest_paths)
    result["orphan_files"] = sorted(manifest_set - payload_paths)
    result["missing_files"] = sorted(payload_paths - manifest_set)
    for row in rows:
        relative = row["path"]
        path = root / Path(*PurePosixPath(relative).parts)
        if not path.is_file():
            continue
        if str(path.stat().st_size) != row["bytes"] or _sha256(path) != row["sha256"]:
            result["hash_mismatches"].append(relative)

    expected_checksum_paths = payload_paths | {"FILE_MANIFEST.csv"}
    checksum_set = set(checksums)
    result["checksum_orphan_files"] = sorted(checksum_set - expected_checksum_paths)
    result["checksum_missing_files"] = sorted(expected_checksum_paths - checksum_set)
    for relative, expected in checksums.items():
        path = root / Path(*PurePosixPath(relative).parts)
        if path.is_file() and _sha256(path) != expected:
            result["checksum_hash_mismatches"].append(relative)
    errors.extend(
        ["manifest closure has orphan or missing files"]
        if result["orphan_files"] or result["missing_files"]
        else []
    )
    errors.extend(
        ["manifest or checksum hash mismatch"]
        if result["hash_mismatches"] or result["checksum_orphan_files"] or result["checksum_missing_files"] or result["checksum_hash_mismatches"]
        else []
    )
    result["errors"] = errors
    result["status"] = "PASS" if not errors else "FAIL"
    return result


def audit_release(root: Path, require_manifest: bool = True) -> dict[str, object]:
    """Run all public-release gates and return a JSON-compatible report."""

    root = Path(root).resolve()
    report: dict[str, Any] = {
        "status": "PASS",
        "public_release": "BLOCKED_MANIFEST" if not require_manifest else "FAIL",
        "pre_manifest": "PASS",
        "level_2": "NOT_REPRODUCED",
        "absolute_path_hits": [],
        "restricted_payload_hits": [],
        "credential_hits": [],
        "zero_hash_hits": [],
        "lf_hits": [],
        "utf8_hits": [],
        "size_hits": [],
        "scan_exclusions": [],
        "errors": [],
    }
    errors: list[str] = []
    try:
        required_errors = _validate_metadata(root)
        errors.extend(required_errors)
    except (OSError, ValueError) as exc:
        errors.append(f"metadata audit failed: {exc}")
    disclosure = _scan_disclosures(root)
    for key, values in disclosure.items():
        report[key] = values
    for key in (
        "absolute_path_hits",
        "restricted_payload_hits",
        "credential_hits",
        "zero_hash_hits",
        "lf_hits",
        "utf8_hits",
        "size_hits",
    ):
        if report[key]:
            errors.append(f"{key} detected")
    errors.extend(_check_licence_scope(root))

    smoke_output: Path | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="green-methanol-audit-") as temp_dir:
            smoke_output = Path(temp_dir) / "smoke.json"
            reproduction = run_reproduction(root, "smoke", smoke_output)
        report["offline_smoke"] = reproduction.get("status")
        report["level_2"] = reproduction.get("level_2_status", "NOT_REPRODUCED")
        report["level_2_status"] = report["level_2"]
        if reproduction.get("status") != "PASS":
            errors.append("offline smoke reproduction failed")
        if report["level_2"] != "NOT_REPRODUCED":
            errors.append("Level 2 must remain NOT_REPRODUCED")
    except (OSError, ValueError, KeyError) as exc:
        report["offline_smoke"] = "FAIL"
        errors.append(f"offline smoke audit failed: {exc}")

    if require_manifest:
        closure = verify_manifest_closure(root)
        report["manifest"] = closure
        if closure.get("status") != "PASS":
            errors.append("manifest/checksum closure failed")
        else:
            report["public_release"] = "PASS"
    else:
        report["manifest"] = {"status": "NOT_RUN"}
    report["pre_manifest"] = "PASS" if not errors or (not require_manifest and all(
        not error.startswith("manifest") and not error.startswith("manifest/checksum") for error in errors
    ) and report.get("offline_smoke") == "PASS") else "FAIL"
    if errors:
        report["status"] = "FAIL"
        report["public_release"] = "FAIL" if require_manifest else "BLOCKED_MANIFEST"
    report["errors"] = sorted(set(errors))
    return report


__all__ = ["audit_release", "verify_manifest_closure"]
