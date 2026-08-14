"""Offline aggregate reproduction for the public release.

The runner deliberately stops at Level 1.  It checks only the released
inventory, aggregate carriers and dictionaries, then recomputes the three
headline percentages from the pooled strict terminal account.  Exact directed
topology, facility mappings, candidate geometry and map carriers are controlled
inputs and are therefore reported as Level 2 ``NOT_REPRODUCED``.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from .contracts import ReleaseRoot, validate_status
from .inventory import CONTROLLED_FIELDS, PUBLIC_SOURCE_FIELDS, validate_inventory


_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MOJIBAKE_MARKERS = ("鈥", "\ufffd")

_CLAIM_FIELDS = (
    "claim_id",
    "scenario_scope",
    "metric",
    "expected_value",
    "unit",
    "tolerance",
    "evidence_boundary",
)
_EXPECTED_CLAIMS = {
    "strict_pipeline_service_gap": "percent",
    "no_terminal_gap": "percentage_points",
    "mapped_unserved_gap": "percentage_points",
}

_ACCOUNT_FIELDS = (
    "scenario_scope",
    "tier",
    "year",
    "aggregation",
    "demand_10kt",
    "pipeline_served_10kt",
    "no_terminal_unserved_10kt",
    "mapped_unserved_10kt",
    "account_status",
    "scope_note",
)
_FIGURE_SPECS: dict[str, tuple[str, ...]] = {
    "figures/source_data/figure-01.csv": (
        "element_id",
        "element_type",
        "label",
        "detail",
        "source_class",
        "target",
    ),
    "figures/source_data/figure-03.csv": (
        "scenario",
        "year",
        "distance_km",
        "pipeline_tonne_km",
        "delivered_tonnes",
    ),
    "figures/source_data/figure-04.csv": (
        "scenario",
        "tier",
        "year",
        "region",
        "demand_methanol_10kt",
        "local_direct_methanol_10kt",
        "pipeline_served_methanol_10kt",
        "served_methanol_10kt",
        "unserved_methanol_10kt",
        "demand_met_pct",
        "pipeline_share_pct",
    ),
    "figures/source_data/figure-05.csv": (
        "panel",
        "scenario",
        "year",
        "metric",
        "value",
        "unit",
        "source_type",
        "style",
        "marker",
        "capacity_relaxation_gain_mt_y",
        "connector_gain_mt_y",
        "capacity_reaches_connector",
    ),
}
_DICTIONARY_PATHS = (
    "data/dictionaries/public_sources.md",
    "data/dictionaries/controlled_inputs.md",
    "data/dictionaries/figure_01.md",
    "data/dictionaries/figure_03.md",
    "data/dictionaries/figure_04.md",
    "data/dictionaries/figure_05.md",
    "data/dictionaries/headline_claims.md",
    "data/dictionaries/panel_map.md",
    "data/dictionaries/terminal_gap_aggregate.md",
)
_PANEL_FIELDS = ("figure", "panel", "status", "source_data", "dictionary", "reason")
_DICTIONARY_SPECS: dict[str, tuple[str, ...]] = {
    "data/dictionaries/public_sources.md": PUBLIC_SOURCE_FIELDS,
    "data/dictionaries/controlled_inputs.md": CONTROLLED_FIELDS,
    "data/dictionaries/figure_01.md": _FIGURE_SPECS["figures/source_data/figure-01.csv"],
    "data/dictionaries/figure_03.md": _FIGURE_SPECS["figures/source_data/figure-03.csv"],
    "data/dictionaries/figure_04.md": _FIGURE_SPECS["figures/source_data/figure-04.csv"],
    "data/dictionaries/figure_05.md": _FIGURE_SPECS["figures/source_data/figure-05.csv"],
    "data/dictionaries/headline_claims.md": _CLAIM_FIELDS,
    "data/dictionaries/panel_map.md": _PANEL_FIELDS,
    "data/dictionaries/terminal_gap_aggregate.md": _ACCOUNT_FIELDS,
}
_REQUIRED_PATHS = (
    "data/public_sources.csv",
    "data/controlled_inputs_metadata.csv",
    "data/author_derived/terminal_gap_aggregate.csv",
    "qa/expected/headline_claims.csv",
    "figures/panel_map.csv",
    *_FIGURE_SPECS.keys(),
    *_DICTIONARY_PATHS,
)
_FIGURE2_REASON = (
    "GS(2023)2767 map source and formal map review are not cleared for public release"
)
_EXPECTED_PANEL_ROWS = (
    (
        "Figure 1",
        "all",
        "aggregate-only",
        "figures/source_data/figure-01.csv",
        "data/dictionaries/figure_01.md",
        "conceptual aggregate workflow only; no topology or facility identifiers",
    ),
    ("Figure 2", "all", "not-run", "", "", _FIGURE2_REASON),
    (
        "Figure 3",
        "all",
        "aggregate-only",
        "figures/source_data/figure-03.csv",
        "data/dictionaries/figure_03.md",
        "scenario-level transport aggregates only; task-level routes are excluded",
    ),
    (
        "Figure 4",
        "c",
        "aggregate-only",
        "figures/source_data/figure-04.csv",
        "data/dictionaries/figure_04.md",
        "regional aggregate accounts only; refinery-proxy entities and coordinates are excluded",
    ),
    (
        "Figure 5",
        "c",
        "aggregate-only",
        "figures/source_data/figure-05.csv",
        "data/dictionaries/figure_05.md",
        "aggregate service-gain panel only; connector identifiers and geometry are excluded",
    ),
)
_WORKFLOW_REASONS = {
    "figure_source_data": (
        "Only reviewed aggregate carriers are released; topology-bearing and coordinate-bearing panels are withheld."
    ),
    "manuscript_artifacts": (
        "The manuscript is not redistributed; this release records only metadata and bounded aggregate evidence."
    ),
    "network_model": (
        "Exact directed topology, facility mappings, candidate geometry and map-review-pending inputs are absent."
    ),
}
_FORBIDDEN_COLUMNS = {
    "candidate_id",
    "candidate_ids",
    "link",
    "links",
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_csv(path: Path, fields: tuple[str, ...], label: str) -> list[dict[str, str]]:
    """Load a UTF-8 LF CSV with an exact header and no malformed rows."""

    payload = path.read_bytes()
    if b"\r" in payload:
        raise ValueError(f"{label} must use LF line endings: {path.as_posix()}")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} is not UTF-8: {path.as_posix()}") from exc
    if any(marker in text for marker in _MOJIBAKE_MARKERS):
        raise ValueError(f"{label} contains a known mojibake marker")
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        actual = tuple(reader.fieldnames or ())
        if actual != fields:
            raise ValueError(f"{label} columns differ: expected={fields}, actual={actual}")
        rows: list[dict[str, str]] = []
        for line_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{label} has malformed row {line_number}")
            rows.append({field: row[field] for field in fields})
    except csv.Error as exc:
        raise ValueError(f"{label} is not valid CSV") from exc
    if not rows:
        raise ValueError(f"{label} cannot be empty")
    return rows


def _validate_utf8_lf(path: Path, label: str) -> None:
    """Reject CRLF and invalid UTF-8 before the Task 2 inventory loader runs."""

    payload = path.read_bytes()
    if b"\r" in payload:
        raise ValueError(f"{label} must use LF line endings: {path.as_posix()}")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} is not UTF-8: {path.as_posix()}") from exc
    if any(marker in text for marker in _MOJIBAKE_MARKERS):
        raise ValueError(f"{label} contains a known mojibake marker")


def _git_head(root: Path) -> str:
    root = Path(root).resolve()
    try:
        top_level = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            check=True,
        )
        top_level_text = top_level.stdout
        if not isinstance(top_level_text, str) or not top_level_text.strip():
            return "unrecorded"
        if Path(top_level_text.strip()).resolve() != root:
            return "unrecorded"
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            check=True,
        )
    except (OSError, ValueError, UnicodeError, subprocess.CalledProcessError):
        return "unrecorded"
    commit_text = completed.stdout
    if not isinstance(commit_text, str):
        return "unrecorded"
    commit = commit_text.strip()
    return commit if _COMMIT_RE.fullmatch(commit) else "unrecorded"


def _resolve(root: Path, relative: str) -> Path:
    return ReleaseRoot(root).resolve(relative)


def _validate_panel_map(root: Path) -> list[dict[str, str]]:
    path = _resolve(root, "figures/panel_map.csv")
    rows = _load_csv(path, _PANEL_FIELDS, "panel map")
    actual_contract = {
        tuple(row[field].strip() for field in _PANEL_FIELDS)
        for row in rows
    }
    expected_contract = set(_EXPECTED_PANEL_ROWS)
    if len(rows) != len(_EXPECTED_PANEL_ROWS) or actual_contract != expected_contract:
        raise ValueError("panel map must match the exact five-row release contract")
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["figure"].strip(), row["panel"].strip())
        if key in seen:
            raise ValueError(f"duplicate panel map row: {key}")
        seen.add(key)
        status = validate_status(row["status"].strip())
        if status not in {"aggregate-only", "not-run"}:
            raise ValueError(f"panel map uses unsupported status: {status}")
        if status == "aggregate-only":
            if not row["source_data"].strip() or not row["dictionary"].strip():
                raise ValueError(f"aggregate panel needs source and dictionary: {key}")
            source = _resolve(root, row["source_data"].strip())
            dictionary = _resolve(root, row["dictionary"].strip())
            if not source.is_file() or not dictionary.is_file():
                raise ValueError(f"panel map target is missing: {key}")
        else:
            if row["source_data"].strip() or row["dictionary"].strip():
                raise ValueError(f"not-run panel cannot expose payload paths: {key}")
            if not row["reason"].strip():
                raise ValueError(f"not-run panel needs a reason: {key}")
    figure2 = [row for row in rows if row["figure"].strip() == "Figure 2"]
    if len(figure2) != 1 or figure2[0]["status"].strip() != "not-run":
        raise ValueError("Figure 2 must have one not-run panel-map row")
    if figure2[0]["reason"].strip() != _FIGURE2_REASON:
        raise ValueError("Figure 2 withholding reason differs from the release contract")
    expected_sources = set(_FIGURE_SPECS)
    mapped_sources = {
        row["source_data"].strip()
        for row in rows
        if row["status"].strip() == "aggregate-only"
    }
    if expected_sources != mapped_sources:
        raise ValueError(
            f"panel map source coverage differs: missing={sorted(expected_sources - mapped_sources)}, "
            f"extra={sorted(mapped_sources - expected_sources)}"
        )
    return rows


def _validate_dictionary(path: Path, fields: tuple[str, ...], label: str) -> None:
    payload = path.read_bytes()
    if b"\r" in payload:
        raise ValueError(f"dictionary must use LF line endings: {label}")
    text = payload.decode("utf-8")
    if any(marker in text for marker in _MOJIBAKE_MARKERS):
        raise ValueError(f"dictionary contains a known mojibake marker: {label}")
    expected_header = (
        "Column",
        "Definition",
        "Unit or codes",
        "Missing-value policy",
        "Derivation",
        "Related panel",
    )
    table_rows: dict[str, tuple[str, ...]] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = tuple(cell.strip() for cell in stripped[1:-1].split("|"))
        if cells == expected_header or all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        if len(cells) != len(expected_header):
            continue
        column = cells[0]
        if column in fields:
            if column in table_rows:
                raise ValueError(f"dictionary repeats column row {column!r}: {label}")
            table_rows[column] = cells[1:]
    missing = [field for field in fields if field not in table_rows]
    extra = sorted(set(table_rows) - set(fields))
    if missing or extra:
        raise ValueError(f"dictionary column rows differ for {label}: missing={missing}, extra={extra}")
    incomplete = [
        field
        for field, values in table_rows.items()
        if any(not value.strip() for value in values)
    ]
    if incomplete:
        raise ValueError(f"dictionary rows have blank metadata for {incomplete}: {label}")


def _recompute_claims(
    account_rows: list[dict[str, str]], claim_rows: list[dict[str, str]]
) -> dict[str, dict[str, Any]]:
    if len(account_rows) != 1:
        raise ValueError("terminal gap aggregate must contain exactly one row")
    selected = [
        row
        for row in account_rows
        if row["scenario_scope"].strip() == "pooled_S1_S8_2060_mid"
    ]
    if len(selected) != 1:
        raise ValueError("terminal gap aggregate must have one pooled S1-S8 mid 2060 row")
    account = selected[0]
    if account["tier"].strip() != "mid" or account["year"].strip() != "2060":
        raise ValueError("terminal gap aggregate denominator must be mid 2060")
    if account["aggregation"].strip() != "demand_weighted":
        raise ValueError("terminal gap aggregate must be demand-weighted")
    if account["account_status"].strip() != "closed":
        raise ValueError("terminal gap aggregate must be closed")
    try:
        values = {
            field: float(account[field])
            for field in (
                "demand_10kt",
                "pipeline_served_10kt",
                "no_terminal_unserved_10kt",
                "mapped_unserved_10kt",
            )
        }
    except (TypeError, ValueError) as exc:
        raise ValueError("terminal gap aggregate has non-numeric accounting values") from exc
    if not all(math.isfinite(value) and value >= 0 for value in values.values()):
        raise ValueError("terminal gap aggregate values must be finite and non-negative")
    demand = values["demand_10kt"]
    if demand <= 0:
        raise ValueError("terminal gap aggregate demand must be positive")
    closure = demand - sum(
        values[field]
        for field in (
            "pipeline_served_10kt",
            "no_terminal_unserved_10kt",
            "mapped_unserved_10kt",
        )
    )
    if abs(closure) > 1e-6:
        raise ValueError(f"terminal gap aggregate does not close: residual={closure}")
    computed = {
        "strict_pipeline_service_gap": (demand - values["pipeline_served_10kt"]) / demand * 100,
        "no_terminal_gap": values["no_terminal_unserved_10kt"] / demand * 100,
        "mapped_unserved_gap": values["mapped_unserved_10kt"] / demand * 100,
    }
    expected: dict[str, dict[str, Any]] = {}
    for row in claim_rows:
        claim_id = row["claim_id"].strip()
        try:
            expected_value = float(row["expected_value"])
            tolerance = float(row["tolerance"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"claim {claim_id!r} has non-numeric expectation") from exc
        if not math.isfinite(expected_value) or not math.isfinite(tolerance) or tolerance < 0:
            raise ValueError(f"claim {claim_id!r} has invalid expectation or tolerance")
        error = abs(computed[claim_id] - expected_value)
        expected[claim_id] = {
            "computed_value": computed[claim_id],
            "expected_value": expected_value,
            "tolerance": tolerance,
            "unit": row["unit"].strip(),
            "absolute_error": error,
            "pass": error <= tolerance,
        }
    return expected


def _base_report(mode: str, root: Path) -> dict[str, Any]:
    workflows = {
        "source_inventory": "reproduced",
        "headline_aggregates": "reproduced",
        "figure_source_data": "aggregate-only",
        "manuscript_artifacts": "hash-only",
        "network_model": "not-run",
    }
    for status in workflows.values():
        validate_status(status)
    return {
        "status": "PASS" if mode == "smoke" else "NOT_REPRODUCED",
        "mode": mode,
        "level_1_status": "PASS",
        "level_2_status": "NOT_REPRODUCED",
        "level_2_reason": (
            "Level 2 requires exact directed pipeline topology, facility-to-trunk/refinery mappings, "
            "candidate-link geometry and map-review-pending inputs that are excluded from this public release."
        ),
        "release_commit": _git_head(root),
        "workflows": workflows,
        "workflow_reasons": dict(_WORKFLOW_REASONS),
        "input_hashes": {},
        "output_hashes": {},
    }


def _validate_workflow_reasons(report: dict[str, Any]) -> None:
    workflows = report.get("workflows", {})
    reasons = report.get("workflow_reasons", {})
    required = {name for name, status in workflows.items() if status != "reproduced"}
    if set(reasons) != required or any(
        not isinstance(reasons[name], str) or not reasons[name].strip() for name in required
    ):
        raise ValueError("workflow reasons must cover every non-reproduced workflow")


def run_reproduction(root: Path, mode: str, output: Path) -> dict[str, object]:
    """Run the offline smoke/full contract and write the report externally."""

    root = Path(root).resolve()
    output = Path(output).resolve()
    if mode not in {"smoke", "full"}:
        raise ValueError(f"unsupported reproduction mode: {mode}")
    if output == root or root in output.parents:
        raise ValueError("reproduction report must be outside the immutable repository")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = _base_report(mode, root)
    errors: list[str] = []
    checked_paths: list[Path] = []
    try:
        _validate_workflow_reasons(report)
        if not _COMMIT_RE.fullmatch(str(report.get("release_commit", ""))):
            raise ValueError("release commit must be a verified 40-character lowercase Git commit")
        for relative in ("data/public_sources.csv", "data/controlled_inputs_metadata.csv"):
            path = _resolve(root, relative)
            _validate_utf8_lf(path, relative)
            checked_paths.append(path)
        validate_inventory(root)
        panel_rows = _validate_panel_map(root)
        checked_paths.append(_resolve(root, "figures/panel_map.csv"))
        claim_rows = _load_csv(
            _resolve(root, "qa/expected/headline_claims.csv"), _CLAIM_FIELDS, "headline claims"
        )
        checked_paths.append(_resolve(root, "qa/expected/headline_claims.csv"))
        claim_ids = {row["claim_id"].strip() for row in claim_rows}
        if len(claim_rows) != len(claim_ids) or claim_ids != set(_EXPECTED_CLAIMS):
            raise ValueError(f"headline claim IDs differ: {sorted(claim_ids)}")
        for row in claim_rows:
            claim_id = row["claim_id"].strip()
            if row["scenario_scope"].strip() != "pooled_S1_S8_2060_mid":
                raise ValueError(f"claim {claim_id!r} has an unexpected denominator")
            if row["unit"].strip() != _EXPECTED_CLAIMS[claim_id]:
                raise ValueError(f"claim {claim_id!r} has an unexpected unit")
        account_path = _resolve(root, "data/author_derived/terminal_gap_aggregate.csv")
        account_rows = _load_csv(account_path, _ACCOUNT_FIELDS, "terminal gap aggregate")
        checked_paths.append(account_path)
        report["claims"] = _recompute_claims(account_rows, claim_rows)
        if not all(item["pass"] for item in report["claims"].values()):
            raise ValueError("one or more headline claim tolerances failed")
        for relative, fields in _FIGURE_SPECS.items():
            path = _resolve(root, relative)
            rows = _load_csv(path, fields, relative)
            checked_paths.append(path)
            columns = {name.casefold() for name in fields}
            forbidden = sorted(columns & _FORBIDDEN_COLUMNS)
            if forbidden:
                raise ValueError(f"figure source-data restricted columns: {forbidden}")
            if relative.endswith("figure-05.csv"):
                if any(row["panel"].strip() != "c" for row in rows):
                    raise ValueError("Figure 5 public source data must be panel c aggregates only")
            if relative.endswith("figure-04.csv") and any(
                row["region"].strip() == "" for row in rows
            ):
                raise ValueError("Figure 4 regional aggregate rows require a region")
        for relative in _DICTIONARY_PATHS:
            path = _resolve(root, relative)
            if not path.is_file():
                raise ValueError(f"missing dictionary: {relative}")
            _validate_dictionary(path, _DICTIONARY_SPECS[relative], relative)
            checked_paths.append(path)
        # A map row is checked above; keep the variable in the report for an
        # auditable count without exposing any private source paths.
        report["checks"] = {
            "inventory": "PASS",
            "panel_map_rows": len(panel_rows),
            "aggregate_csvs": len(_FIGURE_SPECS),
            "dictionaries": len(_DICTIONARY_PATHS),
            "headline_claims": "PASS",
        }
    except (OSError, ValueError, KeyError) as exc:
        errors.append(str(exc))
        report["status"] = "FAIL"
        report["level_1_status"] = "FAIL"
        report["errors"] = errors
    unique_paths = sorted({path.resolve() for path in checked_paths}, key=lambda item: item.as_posix())
    for path in unique_paths:
        if path.is_file():
            report["input_hashes"][path.relative_to(root).as_posix()] = _sha256(path)
    claims_payload = json.dumps(report.get("claims", {}), sort_keys=True, separators=(",", ":"))
    report["output_hashes"] = {
        "recomputed_claims": hashlib.sha256(claims_payload.encode("utf-8")).hexdigest()
    }
    if mode == "full" and report["level_1_status"] == "PASS":
        report["status"] = "NOT_REPRODUCED"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return report


__all__ = ["run_reproduction"]
