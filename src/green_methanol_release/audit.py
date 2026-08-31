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
import io
import json
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .contracts import ReleaseRoot, safe_relative_path
from .inventory import CONTROLLED_DATASET_IDS, load_dataset_registry, validate_inventory
from .reproduce import run_reproduction
from .safety import assert_public_path, audit_tracked_paths


_MANIFEST_FIELDS = ("path", "bytes", "sha256", "purpose", "licence_scope", "data_class")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ZERO_HASH_RE = re.compile(r"(?<![0-9a-f])[0]{64}(?![0-9a-f])")
_CHECKSUM_LINE_RE = re.compile(r"^([0-9a-f]{64})  ([^\r\n]+)$")
_DOI_URL_RE = re.compile(r"https?://(?:dx\.)?doi\.org/[^\s<>\"']+", re.IGNORECASE)
_BARE_DOI_RE = re.compile(r"(?i)\b10\.\d{4,9}/[-._;()/:a-z0-9]+\b")
_PERSISTENT_IDENTIFIER_RE = re.compile(r"(?i)\bpersistent[_ -]?identifier\b")

# Only high-confidence credential forms are used.  The fragments are assembled
# so the scanner's own source does not contain a copyable token-looking value.
_TOKEN_PREFIXES = (
    "gh" + "p_",
    "github" + "_pat_",
    "sk-",
    "xox" + "b-",
    "gl" + "pat-",
    "npm" + "_",
)
_TOKEN_RE = re.compile(
    r"(?:" + "|".join(re.escape(prefix) for prefix in _TOKEN_PREFIXES) + r")[A-Za-z0-9_\-]{20,}"
)
_AWS_KEY_RE = re.compile(r"(?<![A-Z0-9])AKIA[A-Z0-9]{16}(?![A-Z0-9])")
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_CREDENTIAL_URL_RE = re.compile(r"https?://[^\s/@:]+:[^\s/@]+@")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{20,}")
_CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:token|password|secret|api[_-]?key)\s*[:=]\s*[\"']?[A-Za-z0-9_\-+/=.]{8,}"
)

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
    r"(?ix)^\.?(?:"
    r"pipeline[_-]?network[_-]?segments?"
    r"|edge[_-]?flows?"
    r"|facility[_-]?to[_-]?(?:trunk|refinery)"
    r"|refinery[_-]?to[_-]?pipeline[_-]?node[_-]?assignments?"
    r"|candidate[_-].*(?:links?|geometr(?:y|ies))"
    r"|airport[_-]?to[_-]?refinery[_-]?assignments?"
    r"|full[_-]?airport[_-]?demand[_-]?nodes"
    r"|physical[_-]?(?:edges?|nodes?)"
    r"|standard[_-]?map[_-]?gs[_-]?\(?2023\)?[_-]?2767"
    r"|gs[_-]?2023[_-]?2767"
    r")(?:[_-][a-z0-9]+)*(?:\.[a-z0-9][a-z0-9_-]*)*~?$"
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

_CC_BY_ALLOWED_CARRIERS = frozenset(
    {
        "data/author_derived/figure2_aggregate_source.csv",
        "data/author_derived/terminal_gap_aggregate.csv",
        "figures/source_data/figure-01.csv",
        "figures/source_data/figure-03.csv",
        "figures/source_data/figure-04.csv",
        "figures/source_data/figure-05.csv",
        "qa/expected/headline_claims.csv",
        "figures/panel_map.csv",
    }
)
_LICENSE_BULLET_RE = re.compile(r"(?im)^\s*-\s+(.+?)\s*$")
_LICENSE_PATH_RE = re.compile(
    r"(?i)(?<![a-z0-9_./:])(?:\.{0,2}[\\/])?(?:[a-z0-9_.-]+[\\/]+)+[a-z0-9_.-]+(?:\.[a-z0-9]+)?"
)
_LICENSE_ABSOLUTE_RE = re.compile(
    r"(?i)(?<![a-z0-9])(?:[a-z]:[" + chr(92) * 2 + chr(47) + r"])[^`\s]+"
)

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
_TEXT_NAMES = {
    ".gitattributes",
    ".gitignore",
    ".env",
    ".npmrc",
    ".pypirc",
    "Dockerfile",
    "Makefile",
    "LICENSE",
    "LICENSE-DATA",
    "credentials",
    "config",
}
_TEXT_SNIFF_LIMIT = 100 * 1024 * 1024
_SKIP_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".superpowers",
    "src/green_methanol_pipeline_reuse.egg-info",
    "管道数据",
}

_REQUIRED_METADATA = (
    "README.md",
    "DATA_AVAILABILITY.md",
    "CODE_AVAILABILITY.md",
    "MANUSCRIPT_SCOPE.md",
    "CITATION.cff",
    "NOTICE.md",
    "RELEASE_STATUS.md",
    "pyproject.toml",
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


def _verified_registry_carriers(root: Path) -> tuple[set[str], list[str]]:
    """Return hash-verified copy/existing carriers eligible for narrow exemptions."""

    registry_path = root / "data" / "dataset_registry.csv"
    if not registry_path.is_file():
        return set(), []
    try:
        rows = load_dataset_registry(registry_path)
    except (OSError, ValueError):
        return set(), ["dataset registry exemption validation failed"]

    verified: set[str] = set()
    errors: list[str] = []
    for row in rows:
        if row["stage_action"] not in {"copy", "existing"}:
            continue
        relative = row["public_path"]
        try:
            safe = safe_relative_path(relative)
            if not safe.parts:
                raise ValueError("empty public path")
            assert_public_path(Path(relative))
        except ValueError:
            errors.append("dataset registry exemption validation failed")
            continue
        declared = row["sha256"]
        if not _SHA256_RE.fullmatch(declared):
            errors.append("dataset registry carrier hash mismatch")
            continue
        deposited = root.joinpath(*safe.parts)
        if not deposited.is_file():
            errors.append("dataset registry carrier missing")
            continue
        try:
            actual = _sha256(deposited)
        except OSError:
            errors.append("dataset registry carrier missing")
            continue
        if actual != declared:
            errors.append("dataset registry carrier hash mismatch")
            continue
        verified.add(safe.as_posix())
    return verified, sorted(set(errors))


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _is_skipped(path: Path, root: Path) -> bool:
    relative = _relative(root, path)
    return any(
        relative == part or relative.startswith(part + "/") or part in path.parts
        for part in _SKIP_PARTS
    )


def _iter_payload_files(root: Path) -> Iterable[Path]:
    # ``Path.rglob`` cannot prune a directory before descending into it.  Walk
    # top-down so the excluded directory is never traversed or opened.
    payload_files: list[Path] = []
    for directory, dirnames, filenames in os.walk(root, topdown=True):
        directory_path = Path(directory)
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not _is_skipped(directory_path / name, root)
        )
        for filename in sorted(filenames):
            path = directory_path / filename
            if not _is_skipped(path, root):
                payload_files.append(path)
    yield from sorted(payload_files, key=lambda item: item.as_posix())


def _git_tracked_paths(root: Path) -> list[str]:
    """Enumerate tracked names from the Git index without touching payloads."""

    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "-z", "--"],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"git index enumeration failed: {exc}") from exc
    payload = result.stdout or b""
    if isinstance(payload, bytes):
        text = payload.decode("utf-8", errors="surrogateescape")
    else:
        text = str(payload)
    return [path for path in text.split("\0") if path]


def _text_payload(path: Path) -> str | None:
    """Decode a text-like payload; return None for opaque binary files."""

    known_text = path.suffix.casefold() in _TEXT_SUFFIXES or path.name in _TEXT_NAMES
    try:
        payload = path.read_bytes()
    except OSError:
        return None
    if not known_text and (len(payload) > _TEXT_SNIFF_LIMIT or b"\x00" in payload):
        return None
    try:
        return payload.decode("utf-8")
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


def _schema_fields(text: str, suffix: str) -> set[str]:
    """Parse a delimited or JSON payload and return normalized field names."""

    def normalize_field(field: object) -> str:
        return str(field).lstrip("\ufeff").strip().casefold()

    if suffix == ".json":
        value = json.loads(text)

        def collect(item: object) -> set[str]:
            if isinstance(item, dict):
                fields = {normalize_field(key) for key in item}
                for child in item.values():
                    fields.update(collect(child))
                return fields
            if isinstance(item, list):
                fields: set[str] = set()
                for child in item:
                    fields.update(collect(child))
                return fields
            return set()

        return collect(value)

    delimiter = "\t" if suffix == ".tsv" else ","
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    rows = list(reader)
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows[1:]):
        raise ValueError("delimited payload has an invalid row shape")
    return {normalize_field(field) for field in rows[0] if normalize_field(field)}


def _scan_disclosures(
    root: Path, exempt_registry_carriers: Iterable[str] = ()
) -> dict[str, Any]:
    absolute: list[str] = []
    credentials: list[str] = []
    restricted: list[str] = []
    zero_hashes: list[str] = []
    doi_hits: list[str] = []
    format_hits: list[str] = []
    lf_hits: list[str] = []
    utf8_hits: list[str] = []
    size_hits: list[str] = []
    # Report the exact directory-name patterns that are intentionally omitted;
    # payload-like directories are not in this set and are always scanned.
    exclusions = sorted(_SKIP_PARTS)
    registry_exemptions = set(exempt_registry_carriers)

    def inspect(
        label: str,
        text: str,
        *,
        payload_schema: bool = False,
        restricted_text: bool = False,
        suffix: str = "",
        exempt_registry_carrier: bool = False,
    ) -> None:
        if "\r" in text and not exempt_registry_carrier:
            lf_hits.append(label)
        for pattern in (_DRIVE_PATH_RE, _UNC_PATH_RE, _POSIX_HOME_RE):
            if pattern.search(text):
                absolute.append(label)
                break
        if any(
            pattern.search(text)
            for pattern in (
                _TOKEN_RE,
                _AWS_KEY_RE,
                _PRIVATE_KEY_RE,
                _CREDENTIAL_URL_RE,
                _BEARER_RE,
                _CREDENTIAL_ASSIGNMENT_RE,
            )
        ):
            credentials.append(label)
        if _ZERO_HASH_RE.search(text):
            zero_hashes.append(label)
        if _DOI_URL_RE.search(text) or _BARE_DOI_RE.search(text):
            metadata_label = label in {
                "README.md",
                "DATA_AVAILABILITY.md",
                "CODE_AVAILABILITY.md",
                "CITATION.cff",
                "NOTICE.md",
                "MANUSCRIPT_SCOPE.md",
                "RELEASE_STATUS.md",
            }
            if metadata_label or _PERSISTENT_IDENTIFIER_RE.search(text):
                doi_hits.append(label)
        if payload_schema:
            try:
                fieldnames = _schema_fields(text, suffix)
            except (TypeError, ValueError, json.JSONDecodeError, csv.Error):
                format_hits.append(label)
                return
            forbidden = sorted(fieldnames & _RESTRICTED_SCHEMA_FIELDS)
            if forbidden and not exempt_registry_carrier:
                restricted.append(f"{label}:schema={','.join(forbidden)}")
            if _RESTRICTED_NAME_RE.search(text) and not exempt_registry_carrier:
                restricted.append(label)
        elif restricted_text and _RESTRICTED_NAME_RE.search(text) and not exempt_registry_carrier:
            restricted.append(label)

    for path in _iter_payload_files(root):
        relative = _relative(root, path)
        if path.stat().st_size >= 100 * 1024 * 1024:
            size_hits.append(relative)
        exempt_registry_carrier = relative in registry_exemptions
        if _RESTRICTED_NAME_RE.search(path.name) and not exempt_registry_carrier:
            restricted.append(f"{relative}:filename")
        text = _text_payload(path)
        if text is None:
            if path.suffix.casefold() in _TEXT_SUFFIXES or path.name in _TEXT_NAMES:
                utf8_hits.append(relative)
            continue
        suffix = path.suffix.casefold()
        inspect(
            relative,
            text,
            payload_schema=suffix in {".csv", ".tsv", ".json"},
            restricted_text=path.name in _TEXT_NAMES,
            suffix=suffix,
            exempt_registry_carrier=exempt_registry_carrier,
        )

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
        "doi_hits": sorted(set(doi_hits)),
        "format_hits": sorted(set(format_hits)),
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


def _normalize_license_path(value: str) -> str | None:
    """Normalize a candidate licence path and reject unsafe traversal forms."""

    normalized = value.strip().strip("`\"'").rstrip(".,;:!?)]}")
    normalized = normalized.replace("\\", "/")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if (
        not normalized
        or normalized in {".", ".."}
        or normalized.startswith("/")
        or re.match(r"(?i)^[a-z]:", normalized)
        or normalized == ".."
        or normalized.startswith("../")
        or "/../" in normalized
        or normalized.endswith("/..")
    ):
        return None
    return normalized


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
    for relative in ("README.md", "DATA_AVAILABILITY.md", "CODE_AVAILABILITY.md", "RELEASE_STATUS.md"):
        text = _read_text(root, relative)
        if "v1.0.0" not in text:
            errors.append(f"{relative} must identify release version v1.0.0")
        if "Figures 1 and 3-5" not in text:
            errors.append(f"{relative} must state that figure source carriers cover Figures 1 and 3-5")
        if (
            "10.5281/zenodo" in text.casefold()
            or "doi:" in text.casefold()
            or _DOI_URL_RE.search(text)
            or _BARE_DOI_RE.search(text)
        ):
            errors.append(f"{relative} must not claim a DOI")

    metadata_text = "\n".join(
        _read_text(root, relative)
        for relative in (
            "README.md",
            "DATA_AVAILABILITY.md",
            "CODE_AVAILABILITY.md",
            "MANUSCRIPT_SCOPE.md",
            "CITATION.cff",
            "NOTICE.md",
            "RELEASE_STATUS.md",
        )
    )
    obsolete_repository = "7_27" + ".git"
    obsolete_remote_suffix = "green-methanol-pipeline-" + "reuse`"
    if obsolete_repository in metadata_text or obsolete_remote_suffix in metadata_text:
        errors.append("release metadata must not assert the obsolete active repository")
    obsolete_manuscript = "green_methanol_pipeline_reuse_" + "v1.21_en.docx"
    obsolete_digest = "d6c9cec04888efdcd125ef946edad139990e81fb630afc11c7fe94bb2cca" + "4f6a"
    if obsolete_manuscript in metadata_text or obsolete_digest in metadata_text:
        errors.append("release metadata must not bind the obsolete manuscript authority")

    pyproject = _read_text(root, "pyproject.toml")
    project_block = re.search(r"(?ms)^\[project\]\s*(.*?)(?=^\[|\Z)", pyproject)
    version_match = (
        re.search(r"(?m)^version\s*=\s*['\"]([^'\"]+)['\"]\s*$", project_block.group(1))
        if project_block
        else None
    )
    if not version_match or version_match.group(1) != "1.0.0":
        errors.append("pyproject.toml project version must be 1.0.0")

    scope = _read_text(root, "MANUSCRIPT_SCOPE.md")
    for filename in (
        "green_methanol_manuscript_references_v02_2026-08-14_rev04_public_data_code_2026-08-22.docx",
        "green_methanol_supplementary_information_rev04_public_data_code_2026-08-22.docx",
    ):
        if filename not in scope:
            errors.append(f"MANUSCRIPT_SCOPE.md must record the current authority filename: {filename}")
    for digest in (
        "9A93C3FE87F86426D79466872F910A861B8AF06543AA3C4B4B0BD0A258499458",
        "94379F97A40120353EC70762B2C305774865EEE5CA9281B8C5CFFA213F1C1CF0",
    ):
        if digest not in scope:
            errors.append(f"MANUSCRIPT_SCOPE.md must record the current authority SHA-256: {digest}")
    if any(pattern.search(scope) for pattern in (_DRIVE_PATH_RE, _UNC_PATH_RE, _POSIX_HOME_RE)):
        errors.append("MANUSCRIPT_SCOPE.md must not include a local path")

    cff = _read_text(root, "CITATION.cff")
    cff_fields = {
        "title": "Green methanol pipeline reuse: Level-1 release candidate",
        "type": "software",
        "license": "MIT",
        "version": "1.0.0",
        "repository-code": "https://github.com/Chenzhongdaji/green-methanol-pipeline-reuse-public",
    }

    def active_cff_scalar(field: str) -> str | None:
        match = re.search(rf"(?m)^{re.escape(field)}\s*:\s*(.*?)\s*$", cff)
        if not match:
            return None
        value = match.group(1).strip()
        if not value or value.startswith("#"):
            return None
        if value.startswith(('"', "'")) and value.endswith(value[0]) and len(value) >= 2:
            value = value[1:-1]
        return value

    for field, expected in cff_fields.items():
        if active_cff_scalar(field) != expected:
            errors.append(f"CITATION.cff requires active {field}: {expected}")
    author_names = re.findall(r"(?im)^\s*-\s*name\s*:\s*([^\r\n#]+?)\s*$", cff)
    if author_names != ["Research team"]:
        errors.append("CITATION.cff authors must contain only the Research team entity")
    if re.search(
        r"(?im)^\s*(?:-\s*)?(?:email|affiliation|orcid|family-names|given-names)\s*:",
        cff,
    ):
        errors.append("CITATION.cff must not invent personal or ORCID metadata")
    if re.search(r"(?im)^\s*(?:date-released|url)\s*:", cff):
        errors.append("CITATION.cff must not imply an archival release through date-released or url")
    if re.search(r"(?im)^\s*doi\s*:", cff) or _DOI_URL_RE.search(cff) or _BARE_DOI_RE.search(cff):
        errors.append("CITATION.cff must not claim a DOI")
    license_text = _read_text(root, "LICENSE")
    if "MIT License" not in license_text or "Permission is hereby granted, free of charge" not in license_text:
        errors.append("LICENSE must contain the complete MIT notice")
    if re.search(r"(?i)\b(?:cc\s*by|creative commons)\b", license_text):
        errors.append("LICENSE must remain an MIT-only code boundary")
    data_license = _read_text(root, "LICENSE-DATA")
    if "Creative Commons Attribution 4.0 International" not in data_license or "creativecommons.org/licenses/by/4.0/" not in data_license:
        errors.append("LICENSE-DATA must state CC BY 4.0 and its official reference")
    bullet_matches = list(_LICENSE_BULLET_RE.finditer(data_license))
    bullet_candidates = [match.group(1) for match in bullet_matches]
    extracted_candidates = [*bullet_candidates, *_LICENSE_PATH_RE.findall(data_license)]
    normalized_candidates = [_normalize_license_path(item) for item in extracted_candidates if item.strip()]
    unsafe_candidates = {
        item.strip()
        for item, normalized in zip(extracted_candidates, normalized_candidates)
        if normalized is None
        and any(marker in item for marker in ("/", "\\"))
    }
    license_paths = {
        normalized
        for item in bullet_candidates
        if (normalized := _normalize_license_path(item)) is not None
    }
    all_license_paths = {
        normalized for normalized in normalized_candidates if normalized is not None
    }
    canonical_lines = {f"- `{path}`" for path in _CC_BY_ALLOWED_CARRIERS}
    canonical_bullets = {
        line.strip()
        for match in bullet_matches
        if (line := match.group(0).strip()) in canonical_lines
    }
    invalid_bullets = [
        match.group(0).strip()
        for match in bullet_matches
        if match.group(0).strip() not in canonical_lines
    ]
    noncanonical_paths = []
    for match in _LICENSE_PATH_RE.finditer(data_license):
        line_start = data_license.rfind("\n", 0, match.start()) + 1
        line_end = data_license.find("\n", match.end())
        if line_end < 0:
            line_end = len(data_license)
        if data_license[line_start:line_end].strip() not in canonical_lines:
            noncanonical_paths.append(match.group(0))
    if (
        license_paths != _CC_BY_ALLOWED_CARRIERS
        or all_license_paths != _CC_BY_ALLOWED_CARRIERS
        or canonical_bullets != canonical_lines
        or invalid_bullets
        or noncanonical_paths
    ):
        errors.append("LICENSE-DATA CC BY carrier allowlist does not match the exact aggregate paths")
    if unsafe_candidates:
        errors.append("LICENSE-DATA CC BY carrier allowlist rejects unsafe or absolute paths")
    if _LICENSE_ABSOLUTE_RE.search(data_license) or _UNC_PATH_RE.search(data_license):
        errors.append("LICENSE-DATA CC BY carrier allowlist rejects absolute paths")
    forbidden_paths = {
        "data/controlled_inputs_metadata.csv",
        "data/public_sources.csv",
        "data/dictionaries/controlled_inputs.md",
        "data/dictionaries/public_sources.md",
    }
    if license_paths & forbidden_paths or all_license_paths & forbidden_paths or any(path in data_license for path in forbidden_paths):
        errors.append("LICENSE-DATA must exclude controlled and public-source metadata paths")
    data_license_lower = data_license.casefold()
    if not all(
        marker in data_license_lower
        for marker in ("author-generated aggregate data", "public-source", "third-party", "controlled", "not covered")
    ):
        errors.append("LICENSE-DATA must state the controlled/public-source exclusion boundary")
    notice = _read_text(root, "NOTICE.md")
    if "third-party" not in notice.casefold() or "controlled" not in notice.casefold():
        errors.append("NOTICE.md must exclude third-party and controlled materials")
    notice_lower = notice.casefold()
    notice_normalized = re.sub(r"[_-]+", " ", notice_lower)
    protected = r"(?:controlled|restricted|public[- ]source|third[- ]party)"
    grant = r"(?:\bcc\s*by\b|\bcovered\b|\bincluded\b|\blicen(?:s|c)e(?:d|s|ing)?\b)"
    if re.search(
        rf"(?:{protected})[\s\S]{{0,120}}(?:{grant})|(?:{grant})[\s\S]{{0,120}}(?:{protected})",
        notice_normalized,
    ):
        errors.append("NOTICE.md must exclude controlled/restricted/source payloads from CC BY grants")
    if not re.search(rf"{protected}[\s\S]{{0,240}}\bexcluded\b", notice_normalized):
        errors.append("NOTICE.md must explicitly exclude controlled/restricted/source materials")

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
        unsafe_path = False
        try:
            safe_relative_path(normalized["path"])
        except ValueError:
            errors.append(f"unsafe manifest path at row {line_number}")
            unsafe_path = True
        if not unsafe_path:
            try:
                assert_public_path(Path(normalized["path"]))
            except ValueError:
                errors.append(f"forbidden manifest path at row {line_number}")
                unsafe_path = True
        if unsafe_path:
            # Do not retain an unsafe row: verify_manifest_closure must never
            # construct or read a path before the root-relative contract passes.
            continue
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
        try:
            assert_public_path(Path(relative))
        except ValueError:
            errors.append(f"forbidden checksum path at row {line_number}")
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
        "doi_hits": [],
        "format_hits": [],
        "lf_hits": [],
        "utf8_hits": [],
        "size_hits": [],
        "scan_exclusions": [],
        "tracked_forbidden_paths": [],
        "errors": [],
    }
    errors: list[str] = []
    try:
        assert_public_path(root)
    except ValueError as exc:
        report["status"] = "FAIL"
        report["public_release"] = "FAIL" if require_manifest else "BLOCKED_MANIFEST"
        report["pre_manifest"] = "FAIL"
        report["errors"] = [str(exc)]
        return report

    try:
        tracked_forbidden_paths = audit_tracked_paths(_git_tracked_paths(root))
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        tracked_forbidden_paths = []
        errors.append(f"tracked path audit failed: {exc}")
    report["tracked_forbidden_paths"] = tracked_forbidden_paths
    if tracked_forbidden_paths:
        errors.append(
            "tracked forbidden path detected: " + ", ".join(tracked_forbidden_paths)
        )
    try:
        required_errors = _validate_metadata(root)
        errors.extend(required_errors)
    except (OSError, ValueError) as exc:
        errors.append(f"metadata audit failed: {exc}")
    registry_exemptions, registry_errors = _verified_registry_carriers(root)
    errors.extend(registry_errors)
    disclosure = _scan_disclosures(root, registry_exemptions)
    for key, values in disclosure.items():
        report[key] = values
    for key in (
        "absolute_path_hits",
        "restricted_payload_hits",
        "credential_hits",
        "zero_hash_hits",
        "doi_hits",
        "format_hits",
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

    # Freeze the non-manifest gate result before optionally adding closure
    # errors.  A mutated payload must not report a misleading pre-manifest
    # PASS merely because manifest checks were skipped.
    report["pre_manifest"] = "PASS" if not errors else "FAIL"
    if require_manifest:
        closure = verify_manifest_closure(root)
        report["manifest"] = closure
        if closure.get("status") != "PASS":
            errors.append("manifest/checksum closure failed")
        else:
            report["public_release"] = "PASS"
    else:
        report["manifest"] = {"status": "NOT_RUN"}
    if errors:
        report["status"] = "FAIL"
        report["public_release"] = "FAIL" if require_manifest else "BLOCKED_MANIFEST"
    report["errors"] = sorted(set(errors))
    return report


__all__ = ["audit_release", "verify_manifest_closure"]
