"""Safely stage public-input carriers without scanning a source tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

try:
    from green_methanol_release.contracts import ReleaseRoot, safe_relative_path
    from green_methanol_release.inventory import load_dataset_registry
    from green_methanol_release.safety import assert_public_path, resolve_public_path
except ModuleNotFoundError:  # pragma: no cover - used by direct CLI execution
    _SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
    sys.path.insert(0, str(_SRC_ROOT))
    from green_methanol_release.contracts import ReleaseRoot, safe_relative_path
    from green_methanol_release.inventory import load_dataset_registry
    from green_methanol_release.safety import assert_public_path, resolve_public_path


_ALLOWED_ACTIONS = ("copy", "existing", "acquire")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_COMPONENT = "管道数据"
_SOURCE_ID_RE = re.compile(r"^source-id:[A-Za-z0-9][A-Za-z0-9._-]*$")


def _error(
    code: str,
    *,
    dataset_id: str | None = None,
    path: str | None = None,
    message: str | None = None,
) -> dict[str, str]:
    result: dict[str, str] = {"code": code}
    if dataset_id:
        result["dataset_id"] = dataset_id
    if path:
        result["path"] = path
    if message:
        result["message"] = message
    return result


def _empty_report() -> dict[str, object]:
    return {
        "status": "PASS",
        "totals": {
            "datasets": 0,
            "copy": 0,
            "existing": 0,
            "acquire": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
        },
        "datasets": [],
        "errors": [],
    }


def _hash_file(path: Path) -> str:
    path = resolve_public_path(Path(path).parent, Path(path))
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative_path(value: str, *, kind: str) -> str:
    """Validate a repository-relative path without touching the filesystem."""

    relative = safe_relative_path(value)
    if not relative.parts:
        raise ValueError(f"{kind} path must not be empty")
    assert_public_path(Path(value))
    return relative.as_posix()


def _is_stable_source_id(value: str, dataset_id: str) -> bool:
    return bool(_SOURCE_ID_RE.fullmatch(value)) and value == f"source-id:{dataset_id}"


def _registry_error(exc: ValueError) -> dict[str, object]:
    text = str(exc)
    if "public_path" in text and _FORBIDDEN_COMPONENT in text:
        code = "forbidden_destination"
    elif "source_relative_path" in text and _FORBIDDEN_COMPONENT in text:
        code = "forbidden_source"
    elif "sha256" in text:
        code = "invalid_hash"
    else:
        code = "invalid_registry"
    report = _empty_report()
    report["status"] = "FAIL"
    report["errors"] = [_error(code, message="dataset registry validation failed")]
    report["totals"] = {**report["totals"], "errors": 1}
    return report


def _root_error(path: Path, code: str) -> dict[str, object]:
    report = _empty_report()
    report["status"] = "FAIL"
    report["errors"] = [_error(code, message="path enters the excluded directory")]
    report["totals"] = {**report["totals"], "errors": 1}
    return report


def _dataset_entry(row: dict[str, str]) -> dict[str, object]:
    return {
        "dataset_id": row["dataset_id"],
        "public_path": row["public_path"],
        "source_relative_path": row["source_relative_path"],
        "stage_action": row["stage_action"],
        "status": "FAIL",
        "bytes": None,
        "sha256": row["sha256"] or None,
    }


def _entry_error(
    entry: dict[str, object],
    errors: list[dict[str, str]],
    code: str,
    *,
    path: str | None = None,
    message: str | None = None,
) -> None:
    dataset_id = str(entry["dataset_id"])
    errors.append(_error(code, dataset_id=dataset_id, path=path, message=message))


def stage_inputs(
    registry: Path, source_root: Path, release_root: Path
) -> dict[str, object]:
    """Stage registry carriers with fail-closed, non-recursive path handling."""

    registry = Path(registry)
    source_root = Path(source_root)
    release_root = Path(release_root)
    for path, code in (
        (registry, "forbidden_registry"),
        (source_root, "forbidden_source_root"),
        (release_root, "forbidden_release_root"),
    ):
        try:
            assert_public_path(path)
        except ValueError:
            return _root_error(path, code)
    try:
        source_root = resolve_public_path(source_root, Path("."))
        release_root = resolve_public_path(release_root, Path("."))
    except (OSError, ValueError):
        return _root_error(source_root, "forbidden_source_root")

    try:
        rows = load_dataset_registry(registry)
    except ValueError as exc:
        return _registry_error(exc)

    entries: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    action_counts = {action: 0 for action in _ALLOWED_ACTIONS}
    for row in sorted(rows, key=lambda item: item["dataset_id"]):
        entry = _dataset_entry(row)
        entries.append(entry)
        action = row["stage_action"]
        if action not in _ALLOWED_ACTIONS:
            _entry_error(entry, errors, "malformed_action", message="unknown stage action")
            continue
        action_counts[action] += 1

        try:
            public_relative = _relative_path(row["public_path"], kind="destination")
        except ValueError:
            code = (
                "forbidden_destination"
                if _FORBIDDEN_COMPONENT in row["public_path"].replace("\\", "/").split("/")
                else "invalid_destination"
            )
            _entry_error(entry, errors, code, path=row["public_path"])
            continue

        source_value = row["source_relative_path"]
        source_relative = ""
        stable_source_id = _is_stable_source_id(source_value, str(entry["dataset_id"]))
        if source_value:
            if stable_source_id:
                source_relative = source_value
            else:
                try:
                    source_relative = _relative_path(source_value, kind="source")
                except (OSError, ValueError):
                    code = (
                        "forbidden_source"
                        if _FORBIDDEN_COMPONENT in source_value.replace("\\", "/").split("/")
                        else "invalid_source"
                    )
                    _entry_error(entry, errors, code, path=source_value)
                    continue

        if action == "copy" and not source_relative:
            _entry_error(entry, errors, "undeclared_source")
            continue
        if action == "acquire" and source_relative:
            _entry_error(entry, errors, "source_not_empty", path=source_relative)
            continue
        if action == "existing" and source_relative and not stable_source_id:
            _entry_error(entry, errors, "source_not_empty", path=source_relative)
            continue
        if action == "acquire":
            if not row["acquisition_command"]:
                _entry_error(entry, errors, "missing_acquisition_command")
                continue
            entry["status"] = "PASS"
            continue

        declared_hash = row["sha256"]
        if not declared_hash or not _SHA256_RE.fullmatch(declared_hash):
            _entry_error(entry, errors, "invalid_hash")
            continue

        try:
            destination = ReleaseRoot(release_root).resolve(public_relative)
            destination = resolve_public_path(release_root, destination)
        except (OSError, ValueError):
            _entry_error(entry, errors, "invalid_destination", path=public_relative)
            continue

        if action == "copy" and stable_source_id:
            if not destination.is_file():
                _entry_error(entry, errors, "missing_destination", path=public_relative)
                continue
            try:
                actual_hash = _hash_file(destination)
            except OSError:
                _entry_error(entry, errors, "missing_destination", path=public_relative)
                continue
            entry["sha256"] = actual_hash
            if actual_hash != declared_hash:
                _entry_error(entry, errors, "hash_mismatch", path=public_relative)
                continue
            entry["bytes"] = destination.stat().st_size
            entry["status"] = "PASS"
            continue

        if action == "copy":
            source_path = source_root / Path(*source_relative.split("/"))
            try:
                source_path = resolve_public_path(source_root, source_path)
            except (OSError, ValueError):
                _entry_error(entry, errors, "forbidden_source", path=source_relative)
                continue
            if not source_path.is_file():
                _entry_error(entry, errors, "missing_source", path=source_relative)
                continue
            try:
                source_hash = _hash_file(source_path)
            except OSError:
                _entry_error(entry, errors, "missing_source", path=source_relative)
                continue
            entry["sha256"] = source_hash
            if source_hash != declared_hash:
                _entry_error(entry, errors, "hash_mismatch", path=source_relative)
                continue

        if action == "existing":
            if not destination.is_file():
                _entry_error(entry, errors, "missing_destination", path=public_relative)
                continue
            try:
                actual_hash = _hash_file(destination)
            except OSError:
                _entry_error(entry, errors, "missing_destination", path=public_relative)
                continue
            entry["sha256"] = actual_hash
            if actual_hash != declared_hash:
                _entry_error(entry, errors, "hash_mismatch", path=public_relative)
                continue
            entry["bytes"] = destination.stat().st_size
            entry["status"] = "PASS"
            continue

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, destination)
            destination_hash = _hash_file(destination)
        except OSError:
            _entry_error(entry, errors, "copy_failed", path=public_relative)
            continue
        entry["sha256"] = destination_hash
        if destination_hash != declared_hash:
            _entry_error(entry, errors, "destination_hash_mismatch", path=public_relative)
            continue
        entry["bytes"] = destination.stat().st_size
        entry["status"] = "PASS"

    entries.sort(key=lambda item: str(item["dataset_id"]))
    errors.sort(
        key=lambda item: (
            item.get("dataset_id", ""),
            item["code"],
            item.get("path", ""),
        )
    )
    passed = sum(entry["status"] == "PASS" for entry in entries)
    failed = len(entries) - passed
    report: dict[str, object] = {
        "status": "PASS" if not errors else "FAIL",
        "totals": {
            "datasets": len(entries),
            "copy": action_counts["copy"],
            "existing": action_counts["existing"],
            "acquire": action_counts["acquire"],
            "passed": passed,
            "failed": failed,
            "errors": len(errors),
        },
        "datasets": entries,
        "errors": errors,
    }
    return report


def _validate_report_path(path: Path) -> None:
    path = Path(path)
    assert_public_path(path)
    path = resolve_public_path(path.parent, path)
    if not path.name or "\x00" in str(path) or path.is_dir():
        raise ValueError("report path must name a file")


def _write_report(path: Path, report: dict[str, object]) -> None:
    path = Path(path)
    _validate_report_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        _validate_report_path(args.report)
    except (OSError, ValueError):
        return 2
    report = stage_inputs(args.registry, args.source_root, args.release_root)
    try:
        _write_report(args.report, report)
    except (OSError, ValueError):
        return 2
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["main", "stage_inputs"]
