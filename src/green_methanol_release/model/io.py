"""Safe, deterministic I/O helpers for the public model chain."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from ..contracts import ReleaseRoot, safe_relative_path
from ..safety import assert_public_path, resolve_public_path


CSV_ENCODING = "utf-8-sig"


def release_path(root: Path, relative: str) -> Path:
    """Resolve a release-relative path and apply the public boundary guard."""

    relative_path = safe_relative_path(relative)
    assert_public_path(Path(relative))
    resolved = ReleaseRoot(Path(root).resolve()).resolve(relative_path.as_posix())
    assert_public_path(resolved)
    return resolved


def read_csv(root: Path, relative: str, columns: Iterable[str] | None = None) -> pd.DataFrame:
    """Read one public CSV with an optional exact schema check."""

    path = release_path(root, relative)
    if not path.is_file():
        raise ValueError(f"public model input does not exist: {relative}")
    frame = pd.read_csv(path, encoding=CSV_ENCODING)
    if columns is not None:
        expected = tuple(columns)
        actual = tuple(str(column) for column in frame.columns)
        if actual != expected:
            raise ValueError(
                f"public model input schema mismatch for {relative}: "
                f"expected={expected}, actual={actual}"
            )
    if frame.empty:
        raise ValueError(f"public model input is empty: {relative}")
    return frame


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    """Write a UTF-8 CSV with stable LF line endings and no index."""

    path = Path(path).resolve(strict=False)
    assert_public_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def write_json(payload: object, path: Path) -> None:
    """Write sorted, LF-terminated JSON without machine-specific paths."""

    path = Path(path).resolve(strict=False)
    assert_public_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def read_json(root: Path, relative: str) -> object:
    """Read one public JSON carrier through the release-relative boundary."""

    path = release_path(root, relative)
    if not path.is_file():
        raise ValueError(f"public model input does not exist: {relative}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"public model JSON is invalid: {relative}") from exc


def sha256(path: Path) -> str:
    """Return a SHA-256 digest after applying the public boundary guard."""

    path = Path(path).resolve(strict=False)
    assert_public_path(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def hashes_for_paths(root: Path, relatives: Iterable[str]) -> dict[str, str]:
    """Hash release-relative files in canonical path order."""

    values: dict[str, str] = {}
    for relative in sorted(set(relatives)):
        path = release_path(root, relative)
        if not path.is_file():
            raise ValueError(f"model output/input is missing for hashing: {relative}")
        values[relative] = sha256(path)
    return values


def verify_registered_hashes(root: Path, relatives: Iterable[str]) -> dict[str, str]:
    """Verify raw release inputs against the committed dataset registry."""

    from ..inventory import load_dataset_registry

    registry_path = Path(root).resolve() / "data" / "dataset_registry.csv"
    try:
        rows = load_dataset_registry(registry_path)
    except (OSError, ValueError) as exc:
        raise ValueError("cannot validate model inputs against dataset registry") from exc
    by_path = {row["public_path"]: row for row in rows}
    hashes: dict[str, str] = {}
    for relative in sorted(set(relatives)):
        row = by_path.get(relative)
        if row is None:
            raise ValueError(f"model input is not declared in dataset registry: {relative}")
        path = release_path(root, relative)
        if not path.is_file():
            raise ValueError(f"registered model input is missing: {relative}")
        actual = sha256(path)
        if actual != row["sha256"]:
            raise ValueError(f"registered model input hash mismatch: {relative}")
        hashes[relative] = actual
    return hashes


def verify_stage_input_hashes(
    payload: dict[str, Any],
    expected: dict[str, str],
    stage: str,
) -> dict[str, str]:
    """Require a persisted stage audit to match every current input hash."""

    input_hashes = payload.get("input_hashes")
    if not isinstance(input_hashes, dict) or set(input_hashes) != set(expected):
        raise ValueError(f"{stage} audit input hash contract is missing or incomplete")
    if any(
        not isinstance(value, str) or len(value) != 64
        for value in input_hashes.values()
    ):
        raise ValueError(f"{stage} audit contains invalid input hashes")
    for relative, current in expected.items():
        if input_hashes.get(relative) != current:
            raise ValueError(f"{stage} input hash mismatch: {relative}")
    return dict(expected)


def persisted_stage_hashes(
    root: Path,
    output_paths: Iterable[str],
    audit_path: str,
) -> dict[str, str]:
    """Hash persisted stage artifacts, excluding the self-describing audit JSON."""

    return hashes_for_paths(
        root,
        [relative for relative in output_paths if relative != audit_path],
    )


def _canonical_audit_payload(payload: dict[str, Any]) -> bytes:
    unsigned = dict(payload)
    unsigned.pop("audit_sha256", None)
    return json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def finalize_stage_audit(
    payload: dict[str, Any],
    root: Path,
    output_paths: Iterable[str],
    audit_path: str,
) -> dict[str, Any]:
    """Attach persisted output hashes and a canonical self-integrity digest."""

    finalized = dict(payload)
    finalized["output_hashes"] = persisted_stage_hashes(root, output_paths, audit_path)
    finalized.pop("audit_sha256", None)
    finalized["audit_sha256"] = hashlib.sha256(
        _canonical_audit_payload(finalized)
    ).hexdigest()
    return finalized


def verify_persisted_stage(
    root: Path,
    audit_path: str,
    output_paths: Iterable[str],
    stage: str,
) -> dict[str, Any]:
    """Verify persisted artifacts against their upstream stage audit contract."""

    payload = read_json(root, audit_path)
    if not isinstance(payload, dict) or payload.get("stage") != stage:
        raise ValueError(f"{stage} audit is missing or has the wrong stage")
    output_hashes = payload.get("output_hashes")
    expected = persisted_stage_hashes(root, output_paths, audit_path)
    if not isinstance(output_hashes, dict) or set(output_hashes) != set(expected):
        raise ValueError(f"{stage} audit output hash contract is missing or incomplete")
    for relative, actual in expected.items():
        declared = output_hashes.get(relative)
        if declared != actual:
            raise ValueError(f"{stage} persisted artifact hash mismatch: {relative}")
    audit_digest = payload.get("audit_sha256")
    if not isinstance(audit_digest, str) or len(audit_digest) != 64:
        raise ValueError(f"{stage} audit self-integrity hash is missing")
    actual_audit_digest = hashlib.sha256(_canonical_audit_payload(payload)).hexdigest()
    if audit_digest != actual_audit_digest:
        raise ValueError(f"{stage} audit self-integrity hash mismatch")
    return payload


def normalize_province(value: object) -> str:
    """Normalize Chinese province labels to the release's short key."""

    text = str(value).strip()
    suffixes = (
        "维吾尔自治区",
        "壮族自治区",
        "回族自治区",
        "蒙古自治区",
        "特别行政区",
        "自治区",
        "省",
        "市",
    )
    for suffix in suffixes:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    # The generic ``蒙古自治区`` suffix also matches ``内蒙古自治区``;
    # preserve the province name instead of reducing it to ``内``.
    if text == "内":
        text = "内蒙古"
    return text


def finite_float(value: object, field: str) -> float:
    """Parse a finite float and fail closed on malformed values."""

    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"non-numeric model field {field}: {value!r}") from exc
    if not pd.notna(parsed) or not float("-inf") < parsed < float("inf"):
        raise ValueError(f"non-finite model field {field}: {value!r}")
    return parsed


def sorted_frame(frame: pd.DataFrame, keys: Iterable[str]) -> pd.DataFrame:
    """Return a stable, index-free frame in canonical key order."""

    key_columns = list(keys)
    return frame.sort_values(key_columns, kind="mergesort").reset_index(drop=True)
