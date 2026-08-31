"""Deterministic, public-carrier figure builders for the release package."""

from __future__ import annotations

import csv
import hashlib
import math
import re
import textwrap
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch

from .safety import resolve_public_path


FIGURE_DPI = 150
FIGURE_FONT = "Microsoft YaHei"
FIGURE_TEXT = "#233044"
FIGURE_MUTED = "#667085"
FIGURE_GRID = "#D0D5DD"
FIGURE_BLUE = "#1D4ED8"
FIGURE_ORANGE = "#D97706"
FIGURE_GREEN = "#15803D"

_CSV_ENCODING = "utf-8-sig"


def _resolve_standalone_path(path: Path) -> Path:
    """Resolve a direct figure path immediately before filesystem access."""

    path = Path(path)
    root = Path.cwd() if not path.is_absolute() else path.parent
    return resolve_public_path(root, path)


def _configure_plot() -> None:
    plt.rcParams.update(
        {
            "font.family": FIGURE_FONT,
            "font.size": 9,
            "axes.titlesize": 12,
            "axes.labelsize": 9,
            "axes.edgecolor": FIGURE_GRID,
            "axes.labelcolor": FIGURE_TEXT,
            "axes.titlecolor": FIGURE_TEXT,
            "xtick.color": FIGURE_MUTED,
            "ytick.color": FIGURE_MUTED,
            "savefig.facecolor": "white",
            "savefig.edgecolor": "white",
            "axes.unicode_minus": False,
        }
    )


def _read_rows(path: Path, required_columns: Iterable[str]) -> list[dict[str, str]]:
    path = _resolve_standalone_path(Path(path))
    if not path.is_file():
        raise ValueError(f"input carrier does not exist: {path}")
    try:
        with path.open("r", encoding=_CSV_ENCODING, newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            fieldnames = reader.fieldnames or []
            required = tuple(required_columns)
            missing = [column for column in required if column not in fieldnames]
            if missing:
                raise ValueError(f"input carrier missing columns: {', '.join(missing)}")
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ValueError(f"cannot read input carrier: {path}") from exc
    if not rows:
        raise ValueError(f"input carrier is empty: {path}")
    for index, row in enumerate(rows, start=2):
        if None in row or any(row.get(column) is None for column in required):
            raise ValueError(f"input carrier has malformed row {index}")
    return rows


def _number(value: str, *, field: str, row_index: int) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"malformed numeric field {field} at row {row_index}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite numeric field {field} at row {row_index}")
    return parsed


def _coordinate_pair(x_value: str, y_value: str, *, row_index: int) -> tuple[float, float, float, float]:
    """Parse ``lon1,lon2`` and ``lat1,lat2`` coordinate fields."""

    x_parts = str(x_value).split(",")
    y_parts = str(y_value).split(",")
    if len(x_parts) != 2 or len(y_parts) != 2:
        raise ValueError(f"malformed coordinate pair at row {row_index}")
    x1 = _number(x_parts[0].strip(), field="x", row_index=row_index)
    x2 = _number(x_parts[1].strip(), field="x", row_index=row_index)
    y1 = _number(y_parts[0].strip(), field="y", row_index=row_index)
    y2 = _number(y_parts[1].strip(), field="y", row_index=row_index)
    return x1, x2, y1, y2


def _sha256(path: Path) -> str:
    path = _resolve_standalone_path(Path(path))
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _save_figure(fig: plt.Figure, output: Path, *, pdf: bool = False) -> None:
    output = _resolve_standalone_path(Path(output))
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "Creator": "green_methanol_release.figures",
        "Author": "green-methanol-pipeline-reuse-public",
        "Title": "green-methanol release figure",
        "CreationDate": None,
    }
    fig.savefig(
        output,
        format="pdf" if pdf else "png",
        dpi=FIGURE_DPI,
        metadata=metadata,
        bbox_inches="tight",
        pad_inches=0.12,
    )


def _metadata(
    input_path: Path,
    output_path: Path,
    rows: list[dict[str, str]],
    plotted_record_counts: Mapping[str, int],
    **extra: object,
) -> dict[str, object]:
    result: dict[str, object] = {
        "input_row_count": len(rows),
        "output_path": str(Path(output_path)),
        "output_sha256": _sha256(output_path),
        "plotted_record_counts": dict(plotted_record_counts),
        "plotted_records": sum(plotted_record_counts.values()),
    }
    result.update(extra)
    return result


FIGURE_02_COLUMNS = (
    "panel",
    "scenario",
    "year",
    "case",
    "metric",
    "value",
    "unit",
    "denominator",
    "source_type",
    "style",
    "x",
    "y",
    "note",
)
FIGURE_02E_COUNTS = {
    "complete_existing_network": 140,
    "existing_network_design_throughput": 140,
    "model_called_task": 11,
    "province_demand_coverage": 29,
}
FIGURE_02_SUMMARY_PANELS = ("a", "b", "c", "d", "f", "g", "h")
_STYLE_PALETTE = (
    "#1D4ED8",
    "#D97706",
    "#15803D",
    "#7C3AED",
    "#0891B2",
    "#BE123C",
    "#475569",
)
_EDGE_ID_RE = re.compile(
    r"^\s*([A-Za-z0-9_.-]+->[A-Za-z0-9_.-]+)(?:\s*;|\s*$)"
)
_THROUGHPUT_RE = re.compile(
    r"design\s+throughput\s*=\s*"
    r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)",
    re.IGNORECASE,
)


def _line_widths(values: list[float], minimum: float = 0.65, maximum: float = 2.9) -> list[float]:
    lower = min(values)
    upper = max(values)
    if math.isclose(lower, upper):
        return [(minimum + maximum) / 2.0 for _ in values]
    return [minimum + (value - lower) / (upper - lower) * (maximum - minimum) for value in values]


def _figure2_rows(input_path: Path) -> list[dict[str, str]]:
    return _read_rows(Path(input_path), FIGURE_02_COLUMNS)


def _edge_id(note: str, *, row_index: int, kind: str) -> str:
    match = _EDGE_ID_RE.match(note)
    if not match:
        raise ValueError(f"malformed {kind} edge identifier at row {row_index}")
    return match.group(1)


def _note_throughput(note: str, *, row_index: int) -> float | None:
    match = _THROUGHPUT_RE.search(note)
    if match:
        value = _number(match.group(1), field="design throughput", row_index=row_index)
        if value < 0:
            raise ValueError("Figure 2e design throughput must be non-negative")
        return value
    if "design throughput unknown" in note.casefold():
        return None
    raise ValueError(f"missing design throughput annotation at row {row_index}")


def _same_numeric_multiset(left: list[float], right: list[float]) -> bool:
    if len(left) != len(right):
        return False
    return all(math.isclose(a, b, rel_tol=0.0, abs_tol=1e-9) for a, b in zip(sorted(left), sorted(right)))


def _coverage_points(rows: list[dict[str, str]], *, row_offset: int = 2) -> list[tuple[str, float]]:
    points = [
        (
            row["x"].strip(),
            _number(row["value"], field="value", row_index=index),
        )
        for index, row in enumerate(rows, start=row_offset)
    ]
    if any(not label for label, _ in points):
        raise ValueError("Figure 2e coverage label must not be empty")
    if any(value < 0 or value > 100 for _, value in points):
        raise ValueError("Figure 2e province coverage must be between 0 and 100")
    return sorted(points, key=lambda point: (point[0], point[1]))


def _plot_figure_02e(
    rows: list[dict[str, str]], input_path: Path, output_path: Path
) -> dict[str, object]:
    panel_rows = [row for row in rows if row["panel"] == "e"]
    counts = dict(Counter(row["case"] for row in panel_rows))
    if counts != FIGURE_02E_COUNTS:
        raise ValueError(
            "Figure 2e row contract mismatch: "
            f"expected {FIGURE_02E_COUNTS}, got {counts}"
        )

    network_rows = [row for row in panel_rows if row["case"] == "complete_existing_network"]
    throughput_rows = [
        row for row in panel_rows if row["case"] == "existing_network_design_throughput"
    ]
    task_rows = [row for row in panel_rows if row["case"] == "model_called_task"]
    coverage_rows = [row for row in panel_rows if row["case"] == "province_demand_coverage"]

    network_records: list[tuple[str, tuple[float, float, float, float], float | None, str]] = []
    for index, row in enumerate(network_rows, start=2):
        network_records.append(
            (
                _edge_id(row["note"], row_index=index, kind="network"),
                _coordinate_pair(row["x"], row["y"], row_index=index),
                _note_throughput(row["note"], row_index=index),
                row["note"],
            )
        )
    network_records.sort(key=lambda record: (record[0], record[1], record[3]))
    network_coordinates = [record[1] for record in network_records]
    note_throughput_values = [record[2] for record in network_records]

    task_records: list[tuple[str, tuple[float, float, float, float], float, str]] = []
    for index, row in enumerate(task_rows, start=2):
        task_records.append(
            (
                _edge_id(row["note"], row_index=index, kind="task"),
                _coordinate_pair(row["x"], row["y"], row_index=index),
                _number(row["value"], field="value", row_index=index),
                row["note"],
            )
        )
    task_records.sort(key=lambda record: (record[0], record[1], record[3]))
    task_coordinates = [record[1] for record in task_records]
    task_values = [record[2] for record in task_records]
    network_edges: dict[str, list[tuple[float, float, float, float]]] = {}
    for edge_id, coordinate, _, _ in network_records:
        network_edges.setdefault(edge_id, []).append(coordinate)
    for edge_id, coordinate, _, _ in task_records:
        if edge_id not in network_edges or coordinate not in network_edges[edge_id]:
            raise ValueError(f"model task edge is not an existing network edge: {edge_id}")

    throughput_values: list[float | None] = []
    for index, row in enumerate(sorted(throughput_rows, key=lambda item: item["x"]), start=2):
        throughput_values.append(
            None
            if not row["value"].strip()
            else _number(row["value"], field="value", row_index=index)
        )
    note_known = [value for value in note_throughput_values if value is not None]
    carrier_known = [value for value in throughput_values if value is not None]
    if len(note_known) != len(carrier_known) or not _same_numeric_multiset(note_known, carrier_known):
        raise ValueError("Figure 2e design throughput note/carrier mismatch")
    if note_throughput_values.count(None) != throughput_values.count(None):
        raise ValueError("Figure 2e unknown design throughput count mismatch")
    coverage_points = _coverage_points(coverage_rows)
    coverage_names = [point[0] for point in coverage_points]
    coverage_values = [point[1] for point in coverage_points]
    if len(throughput_values) != len(network_coordinates):
        raise ValueError("Figure 2e network and throughput rows cannot be matched")

    _configure_plot()
    fig = plt.figure(figsize=(13.4, 8.4))
    map_axis = fig.add_axes((0.06, 0.17, 0.67, 0.70))
    coverage_axis = fig.add_axes((0.79, 0.17, 0.18, 0.70))

    available_throughput = [value for value in note_throughput_values if value is not None]
    available_widths = _line_widths(available_throughput)
    widths_by_value = dict(zip(available_throughput, available_widths))
    network_widths = [
        widths_by_value[value] if value is not None else 0.65 for value in note_throughput_values
    ]
    for (x1, x2, y1, y2), linewidth in zip(network_coordinates, network_widths):
        map_axis.plot(
            (x1, x2),
            (y1, y2),
            color="#B8C1CC",
            linewidth=linewidth,
            alpha=0.75,
            solid_capstyle="round",
            zorder=1,
        )

    task_widths = _line_widths(task_values, minimum=1.5, maximum=3.7)
    for (x1, x2, y1, y2), linewidth in zip(task_coordinates, task_widths):
        map_axis.plot(
            (x1, x2),
            (y1, y2),
            color=FIGURE_ORANGE,
            linewidth=linewidth,
            alpha=0.95,
            solid_capstyle="round",
            zorder=3,
        )
        map_axis.scatter((x2,), (y2,), s=12, color=FIGURE_ORANGE, zorder=4)

    all_x = [value for coordinate in network_coordinates + task_coordinates for value in coordinate[:2]]
    all_y = [value for coordinate in network_coordinates + task_coordinates for value in coordinate[2:]]
    x_pad = max((max(all_x) - min(all_x)) * 0.04, 0.5)
    y_pad = max((max(all_y) - min(all_y)) * 0.04, 0.5)
    map_axis.set_xlim(min(all_x) - x_pad, max(all_x) + x_pad)
    map_axis.set_ylim(min(all_y) - y_pad, max(all_y) + y_pad)
    map_axis.set_aspect("equal", adjustable="box")
    map_axis.set_xlabel("Longitude-like analytical coordinate")
    map_axis.set_ylabel("Latitude-like analytical coordinate")
    map_axis.set_title("Coordinate-based network rendering", loc="left", weight="bold")
    map_axis.grid(False)

    coverage_axis.barh(
        list(range(len(coverage_points))),
        coverage_values,
        color="#93C5FD",
        edgecolor="#1D4ED8",
        linewidth=0.35,
    )
    coverage_axis.set_yticks(list(range(len(coverage_points))))
    coverage_axis.set_yticklabels(coverage_names, fontsize=6)
    coverage_axis.invert_yaxis()
    coverage_axis.set_xlim(0, 100)
    coverage_axis.set_xlabel("%", labelpad=1)
    coverage_axis.set_title("Province demand coverage\n(29 carrier rows)", fontsize=9, weight="bold")
    coverage_axis.grid(axis="x", color="#E5E7EB", linewidth=0.5)
    coverage_axis.set_axisbelow(True)

    legend = [
        Line2D([], [], color="#B8C1CC", linewidth=2.2, label="Existing network (140 directed segments)"),
        Line2D([], [], color=FIGURE_ORANGE, linewidth=2.6, label="Model-called task (11 segments)"),
        Patch(facecolor="#93C5FD", edgecolor="#1D4ED8", label="Province coverage summary (29 rows)"),
    ]
    fig.legend(handles=legend, loc="lower left", bbox_to_anchor=(0.06, 0.055), frameon=False, ncol=2)
    fig.suptitle("Figure 2e | Existing network and model-called task", color=FIGURE_TEXT, weight="bold", y=0.96)
    fig.text(
        0.06,
        0.018,
        "Analytical coordinates; no official basemap",
        color=FIGURE_TEXT,
        fontsize=9,
        weight="bold",
    )
    fig.text(
        0.60,
        0.018,
        "Line width follows the matched design-throughput carrier field.",
        color=FIGURE_MUTED,
        fontsize=8,
    )
    _save_figure(fig, Path(output_path))
    sibling_pdf = Path(output_path).with_suffix(".pdf")
    _save_figure(fig, sibling_pdf, pdf=True)
    plt.close(fig)
    return _metadata(
        input_path,
        output_path,
        rows,
        FIGURE_02E_COUNTS,
        sibling_pdf_path=str(sibling_pdf),
        sibling_pdf_sha256=_sha256(sibling_pdf),
        coordinate_note="Analytical coordinates; no official basemap",
        coverage_summary=[{"label": label, "value": value} for label, value in coverage_points],
    )


def _plot_figure_02_summary(
    rows: list[dict[str, str]], input_path: Path, output_path: Path
) -> dict[str, object]:
    panel_rows = [row for row in rows if row["panel"] in FIGURE_02_SUMMARY_PANELS]
    panel_counts = {panel: sum(row["panel"] == panel for row in panel_rows) for panel in FIGURE_02_SUMMARY_PANELS}
    if any(count == 0 for count in panel_counts.values()):
        missing = [panel for panel, count in panel_counts.items() if count == 0]
        raise ValueError(f"Figure 2 summary has empty panel(s): {', '.join(missing)}")
    for index, row in enumerate(panel_rows, start=2):
        value_field = row["value"].strip()
        if not value_field and row["panel"] == "a" and row["style"] == "trajectory":
            value_field = row["y"].strip()
        if value_field:
            _number(value_field, field="value", row_index=index)
        elif not (
            row["panel"] == "a"
            and row["style"] == "trajectory"
            and row["note"].strip().startswith("N.A.")
        ):
            raise ValueError(f"malformed numeric field value at row {index}")

    _configure_plot()
    fig, axes = plt.subplots(4, 2, figsize=(14.4, 11.0), squeeze=False)
    axes_flat = list(axes.flat)
    rendered_counts: dict[str, int] = {}
    for axis, panel in zip(axes_flat, FIGURE_02_SUMMARY_PANELS):
        current = [row for row in panel_rows if row["panel"] == panel]
        styles = sorted({row["style"] for row in current})
        style_colors = {style: _STYLE_PALETTE[index % len(_STYLE_PALETTE)] for index, style in enumerate(styles)}
        rendered_count = 0
        if panel == "a":
            trajectory_count = 0
            for scenario in sorted({row["scenario"] for row in current}):
                trajectory = [
                    row
                    for row in current
                    if row["scenario"] == scenario
                    and row["style"] == "trajectory"
                    and row["y"].strip()
                ]
                trajectory = sorted(trajectory, key=lambda row: _number(row["x"], field="x", row_index=2))
                if trajectory:
                    years = [_number(row["x"], field="x", row_index=2) for row in trajectory]
                    values = [_number(row["y"], field="y", row_index=2) for row in trajectory]
                    axis.plot(
                        years,
                        values,
                        marker="o",
                        markersize=3.2,
                        linewidth=1.2,
                        color=style_colors["trajectory"],
                        alpha=0.82,
                        label=scenario,
                    )
                    trajectory_count += len(trajectory)
            callouts = sorted(
                (row for row in current if row["style"] != "trajectory"),
                key=lambda row: (row["scenario"], row["x"], row["metric"], row["style"], row["note"]),
            )
            for row in callouts:
                if row["style"] != "trajectory":
                    x_value = _number(row["x"], field="x", row_index=2)
                    y_value = _number(row["y"], field="y", row_index=2)
                    axis.scatter((x_value,), (y_value,), color=style_colors[row["style"]], s=30, marker="D")
            rendered_count = trajectory_count + len(callouts)
            axis.set_xlabel("Year")
            axis.set_ylabel("Value (%)")
            if trajectory_count:
                axis.legend(frameon=False, fontsize=7, ncol=2)
        else:
            ordered = sorted(
                enumerate(current),
                key=lambda pair: (
                    pair[1]["scenario"],
                    pair[1]["x"],
                    pair[1]["metric"],
                    pair[1]["style"],
                    pair[0],
                ),
            )
            labels = [row["x"].strip() or row["scenario"].strip() for _, row in ordered]
            values = [_number(row["value"], field="value", row_index=2) for _, row in ordered]
            colors = [style_colors[row["style"]] for _, row in ordered]
            axis.bar(list(range(len(values))), values, color=colors, width=0.82)
            rendered_count = len(values)
            axis.set_xticks(list(range(len(labels))))
            axis.set_xticklabels(labels, rotation=90 if len(labels) > 12 else 0, fontsize=6 if len(labels) > 12 else 7)
            axis.set_ylabel(str(current[0]["unit"]).strip() or "value")
            if len(styles) > 1:
                handles = [Patch(facecolor=style_colors[style], label=style) for style in styles]
                axis.legend(handles=handles, frameon=False, fontsize=6, loc="best")
        if rendered_count <= 0:
            plt.close(fig)
            raise ValueError(f"Figure 2 summary panel {panel} has no rendered records")
        rendered_counts[f"panel_{panel}"] = rendered_count
        axis.set_title(f"Panel {panel}", loc="left", weight="bold")
        axis.grid(axis="y", color="#E5E7EB", linewidth=0.5)
        axis.set_axisbelow(True)
    axes_flat[-1].axis("off")
    fig.suptitle("Figure 2 | Public carrier summary (panels a-d and f-h)", color=FIGURE_TEXT, weight="bold", y=0.995)
    fig.text(0.02, 0.012, "Panel values and categories are read directly from the public Figure 2 carrier.", color=FIGURE_MUTED, fontsize=8)
    fig.tight_layout(rect=(0.02, 0.03, 1, 0.97))
    _save_figure(fig, Path(output_path))
    plt.close(fig)
    return _metadata(
        input_path,
        output_path,
        rows,
        {f"panel_{panel}": count for panel, count in panel_counts.items()},
        selected_panels=list(FIGURE_02_SUMMARY_PANELS),
        rendered_record_counts=rendered_counts,
    )


def build_figure_02(
    input_path: Path,
    output_path: Path,
    *,
    panel: str | None = None,
    panels: str | None = None,
) -> dict[str, object]:
    """Build Figure 2 panel e or the a-d/f-h aggregate summary."""

    if (panel is None) == (panels is None):
        raise ValueError("provide exactly one of panel or panels")
    rows = _figure2_rows(Path(input_path))
    if panel is not None:
        if panel != "e":
            raise ValueError("Figure 2 only accepts --panel e")
        return _plot_figure_02e(rows, Path(input_path), Path(output_path))
    if panels != "a-d,f-h":
        raise ValueError("Figure 2 summary only accepts --panels a-d,f-h")
    return _plot_figure_02_summary(rows, Path(input_path), Path(output_path))


def _read_exact_rows(path: Path, required_columns: Iterable[str]) -> list[dict[str, str]]:
    """Read a public carrier with an exact header and non-empty record set."""

    path = _resolve_standalone_path(Path(path))
    rows = _read_rows(path, required_columns)
    with path.open("r", encoding=_CSV_ENCODING, newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        actual = tuple(reader.fieldnames or ())
    expected = tuple(required_columns)
    if actual != expected:
        raise ValueError(
            f"input carrier columns differ: expected={expected}, actual={actual}"
        )
    return rows


def _text(value: str, *, field: str, row_index: int, allow_blank: bool = False) -> str:
    text_value = str(value).strip()
    if not text_value and not allow_blank:
        raise ValueError(f"blank text field {field} at row {row_index}")
    return text_value


def _year(value: str, *, row_index: int) -> int:
    parsed = _number(value, field="year", row_index=row_index)
    if not parsed.is_integer():
        raise ValueError(f"year must be an integer at row {row_index}")
    return int(parsed)


def _nonnegative_number(value: str, *, field: str, row_index: int) -> float:
    parsed = _number(value, field=field, row_index=row_index)
    if parsed < 0:
        raise ValueError(f"{field} must be non-negative at row {row_index}")
    return parsed


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-7, abs_tol=1e-6)


def _scenario_key(value: str) -> tuple[int, str]:
    match = re.fullmatch(r"S(\d+)", value.strip(), flags=re.IGNORECASE)
    if match:
        return int(match.group(1)), value.strip()
    return (10**9, value.strip())


FIGURE_01_COLUMNS = (
    "element_id",
    "element_type",
    "label",
    "detail",
    "source_class",
    "target",
)
FIGURE_01_TYPES = ("evidence", "allocation", "output", "transform", "metric", "decision")
FIGURE_01_COLORS = {
    "evidence": "#DBEAFE",
    "allocation": "#FEF3C7",
    "output": "#DCFCE7",
    "transform": "#EDE9FE",
    "metric": "#CFFAFE",
    "decision": "#FCE7F3",
}


def _plot_figure_01(
    rows: list[dict[str, str]], input_path: Path, output_path: Path
) -> dict[str, object]:
    records: list[dict[str, str]] = []
    labels: dict[str, str] = {}
    for index, row in enumerate(rows, start=2):
        element_id = _text(row["element_id"], field="element_id", row_index=index)
        element_type = _text(row["element_type"], field="element_type", row_index=index)
        if element_type not in FIGURE_01_TYPES:
            raise ValueError(f"unknown Figure 1 element_type at row {index}: {element_type}")
        label = _text(row["label"], field="label", row_index=index)
        detail = _text(row["detail"], field="detail", row_index=index)
        source_class = _text(row["source_class"], field="source_class", row_index=index)
        if source_class not in {"model_output", "post_model_transform"}:
            raise ValueError(f"unknown Figure 1 source_class at row {index}: {source_class}")
        if element_id in {item["element_id"] for item in records}:
            raise ValueError(f"duplicate element_id at row {index}: {element_id}")
        if label in labels:
            raise ValueError(f"duplicate Figure 1 label at row {index}: {label}")
        labels[label] = element_id
        records.append(
            {
                "element_id": element_id,
                "element_type": element_type,
                "label": label,
                "detail": detail,
                "source_class": source_class,
                "target": _text(row["target"], field="target", row_index=index, allow_blank=True),
            }
        )

    links: list[tuple[str, str]] = []
    for index, record in enumerate(records, start=2):
        target = record["target"]
        if target:
            if target not in labels:
                raise ValueError(f"Figure 1 target is not a known label at row {index}: {target}")
            links.append((record["element_id"], labels[target]))

    lane_records = {
        lane: sorted(
            (record for record in records if record["element_type"] == lane),
            key=lambda item: (item["element_id"], item["label"]),
        )
        for lane in FIGURE_01_TYPES
    }
    positions: dict[str, tuple[float, float]] = {}
    for lane_index, lane in enumerate(FIGURE_01_TYPES):
        current = lane_records[lane]
        for row_index, record in enumerate(current):
            y = (len(current) - 1) / 2.0 - row_index
            positions[record["element_id"]] = (float(lane_index), y)

    _configure_plot()
    fig, axis = plt.subplots(figsize=(16.0, 10.0))
    axis.set_xlim(-0.65, len(FIGURE_01_TYPES) - 0.35)
    max_rows = max(len(current) for current in lane_records.values())
    axis.set_ylim(-max_rows / 2.0 - 1.0, max_rows / 2.0 + 1.35)
    axis.axis("off")

    for lane_index, lane in enumerate(FIGURE_01_TYPES):
        axis.text(
            lane_index,
            max_rows / 2.0 + 0.85,
            lane.capitalize(),
            ha="center",
            va="center",
            color=FIGURE_TEXT,
            weight="bold",
            fontsize=10,
        )

    for source_id, target_id in sorted(links):
        source_x, source_y = positions[source_id]
        target_x, target_y = positions[target_id]
        arrow = FancyArrowPatch(
            (source_x, source_y),
            (target_x, target_y),
            arrowstyle="-|>",
            mutation_scale=8,
            linewidth=0.65,
            color=FIGURE_MUTED,
            alpha=0.65,
            connectionstyle="arc3,rad=0.04",
            zorder=1,
        )
        axis.add_patch(arrow)

    for record in sorted(records, key=lambda item: positions[item["element_id"]]):
        x, y = positions[record["element_id"]]
        box = FancyBboxPatch(
            (x - 0.43, y - 0.27),
            0.86,
            0.54,
            boxstyle="round,pad=0.03,rounding_size=0.05",
            linewidth=0.75,
            edgecolor=FIGURE_TEXT,
            facecolor=FIGURE_01_COLORS[record["element_type"]],
            zorder=2,
        )
        axis.add_patch(box)
        axis.text(
            x,
            y,
            textwrap.fill(record["label"], width=15),
            ha="center",
            va="center",
            color=FIGURE_TEXT,
            fontsize=7.0,
            fontfamily="DejaVu Sans",
            zorder=3,
        )

    legend = [
        Patch(facecolor=FIGURE_01_COLORS[lane], edgecolor=FIGURE_TEXT, label=lane.capitalize())
        for lane in FIGURE_01_TYPES
    ]
    axis.legend(handles=legend, loc="lower center", bbox_to_anchor=(0.5, -0.055), ncol=6, frameon=False)
    fig.suptitle(
        "Figure 1 | Public aggregate workflow and decision chain",
        color=FIGURE_TEXT,
        weight="bold",
        y=0.98,
    )
    fig.text(
        0.5,
        0.015,
        "Conceptual labels and target links are read directly from the public carrier; no topology or quantitative result is added.",
        ha="center",
        color=FIGURE_MUTED,
        fontsize=8,
    )
    fig.tight_layout(rect=(0.01, 0.035, 0.99, 0.96))
    _save_figure(fig, Path(output_path))
    plt.close(fig)
    return _metadata(
        input_path,
        output_path,
        rows,
        {"nodes": len(records), "links": len(links)},
        lanes=list(FIGURE_01_TYPES),
        link_targets_derived=True,
        quantitative_results_added=False,
    )


def build_figure_01(input_path: Path, output_path: Path) -> dict[str, object]:
    """Build the labelled conceptual workflow from the Figure 1 carrier."""

    rows = _read_exact_rows(Path(input_path), FIGURE_01_COLUMNS)
    return _plot_figure_01(rows, Path(input_path), Path(output_path))


FIGURE_03_COLUMNS = (
    "scenario",
    "year",
    "distance_km",
    "pipeline_tonne_km",
    "delivered_tonnes",
)


def _plot_figure_03(
    rows: list[dict[str, str]], input_path: Path, output_path: Path
) -> dict[str, object]:
    records: list[dict[str, object]] = []
    seen_scenarios: set[str] = set()
    for index, row in enumerate(rows, start=2):
        scenario = _text(row["scenario"], field="scenario", row_index=index)
        if scenario in seen_scenarios:
            raise ValueError(f"duplicate Figure 3 scenario at row {index}: {scenario}")
        seen_scenarios.add(scenario)
        record = {
            "scenario": scenario,
            "year": _year(row["year"], row_index=index),
            "distance_km": _nonnegative_number(row["distance_km"], field="distance_km", row_index=index),
            "pipeline_tonne_km": _nonnegative_number(
                row["pipeline_tonne_km"], field="pipeline_tonne_km", row_index=index
            ),
            "delivered_tonnes": _nonnegative_number(
                row["delivered_tonnes"], field="delivered_tonnes", row_index=index
            ),
        }
        records.append(record)
    records.sort(key=lambda item: _scenario_key(str(item["scenario"])))
    scenarios = [str(record["scenario"]) for record in records]
    distances = [float(record["distance_km"]) for record in records]
    tonne_km = [float(record["pipeline_tonne_km"]) for record in records]
    delivered = [float(record["delivered_tonnes"]) for record in records]
    colors = [_STYLE_PALETTE[index % len(_STYLE_PALETTE)] for index in range(len(records))]

    _configure_plot()
    fig, (scatter_axis, bar_axis) = plt.subplots(
        1, 2, figsize=(14.0, 6.8), gridspec_kw={"width_ratios": (1.25, 1.0)}
    )
    maximum_tonne_km = max(tonne_km, default=0.0)
    sizes = [80.0 + (260.0 * value / maximum_tonne_km if maximum_tonne_km else 0.0) for value in tonne_km]
    scatter_axis.scatter(
        distances,
        [value / 1e6 for value in delivered],
        s=sizes,
        c=colors,
        edgecolors="white",
        linewidths=0.8,
        alpha=0.9,
        zorder=3,
    )
    for scenario, x_value, y_value in zip(scenarios, distances, delivered):
        scatter_axis.annotate(
            scenario,
            (x_value, y_value / 1e6),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
            color=FIGURE_TEXT,
        )
    scatter_axis.set_xlabel("Flow-weighted distance (km)")
    scatter_axis.set_ylabel("Pipeline-delivered methanol (million tonnes)")
    scatter_axis.set_title("Distance and delivered volume", loc="left", weight="bold")
    scatter_axis.grid(color="#E5E7EB", linewidth=0.5)
    scatter_axis.set_axisbelow(True)

    bar_axis.barh(
        list(range(len(records))),
        [value / 1e9 for value in tonne_km],
        color=colors,
        edgecolor="white",
        linewidth=0.5,
    )
    bar_axis.set_yticks(list(range(len(records))))
    bar_axis.set_yticklabels(scenarios)
    bar_axis.invert_yaxis()
    bar_axis.set_xlabel("Pipeline task (billion tonne-km)")
    bar_axis.set_title("Scenario transport task", loc="left", weight="bold")
    bar_axis.grid(axis="x", color="#E5E7EB", linewidth=0.5)
    bar_axis.set_axisbelow(True)
    size_legend = [
        Line2D(
            [],
            [],
            marker="o",
            linestyle="",
            markersize=size,
            markerfacecolor=FIGURE_MUTED,
            markeredgecolor="white",
            label=f"{value:g} billion tonne-km",
        )
        for size, value in ((6.0, 1.0), (11.0, 10.0))
    ]
    scatter_axis.legend(handles=size_legend, frameon=False, title="Bubble area encodes", loc="best")
    fig.suptitle(
        "Figure 3 | Scenario-level pipeline distance, task and delivery",
        color=FIGURE_TEXT,
        weight="bold",
        y=0.98,
    )
    fig.text(
        0.5,
        0.015,
        "Public scenario aggregates; values are model-derived and are not observations of qualified physical segments.",
        ha="center",
        color=FIGURE_MUTED,
        fontsize=8,
    )
    fig.tight_layout(rect=(0.02, 0.04, 0.98, 0.95))
    _save_figure(fig, Path(output_path))
    plt.close(fig)
    return _metadata(
        input_path,
        output_path,
        rows,
        {"scenario_points": len(records), "transport_task_bars": len(records)},
        scenarios=scenarios,
        year_values=sorted({int(record["year"]) for record in records}),
        bubble_field="pipeline_tonne_km",
    )


def build_figure_03(input_path: Path, output_path: Path) -> dict[str, object]:
    """Build the scenario-level Figure 3 aggregate comparison."""

    rows = _read_exact_rows(Path(input_path), FIGURE_03_COLUMNS)
    return _plot_figure_03(rows, Path(input_path), Path(output_path))


FIGURE_04_COLUMNS = (
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
)
FIGURE_04_REGIONS = ("NC", "NE", "EC", "CC", "SC", "SW", "NW")


def _plot_figure_04(
    rows: list[dict[str, str]], input_path: Path, output_path: Path
) -> dict[str, object]:
    numeric_fields = (
        "demand_methanol_10kt",
        "local_direct_methanol_10kt",
        "pipeline_served_methanol_10kt",
        "served_methanol_10kt",
        "unserved_methanol_10kt",
        "demand_met_pct",
        "pipeline_share_pct",
    )
    records: list[dict[str, object]] = []
    seen_keys: set[tuple[str, str, int, str]] = set()
    for index, row in enumerate(rows, start=2):
        scenario = _text(row["scenario"], field="scenario", row_index=index)
        tier = _text(row["tier"], field="tier", row_index=index)
        year = _year(row["year"], row_index=index)
        region = _text(row["region"], field="region", row_index=index)
        key = (scenario, tier, year, region)
        if key in seen_keys:
            raise ValueError(f"duplicate Figure 4 scenario-region row at row {index}: {key}")
        seen_keys.add(key)
        parsed = {field: _nonnegative_number(row[field], field=field, row_index=index) for field in numeric_fields}
        for field in ("demand_met_pct", "pipeline_share_pct"):
            if parsed[field] > 100.0 + 1e-6:
                raise ValueError(f"{field} must be between 0 and 100 at row {index}")
        if not _close(
            parsed["served_methanol_10kt"],
            parsed["local_direct_methanol_10kt"] + parsed["pipeline_served_methanol_10kt"],
        ):
            raise ValueError(f"Figure 4 served account does not close at row {index}")
        if not _close(
            parsed["demand_methanol_10kt"],
            parsed["served_methanol_10kt"] + parsed["unserved_methanol_10kt"],
        ):
            raise ValueError(f"Figure 4 demand account does not close at row {index}")
        demand = parsed["demand_methanol_10kt"]
        served = parsed["served_methanol_10kt"]
        expected_demand_met = 0.0 if demand == 0 else served / demand * 100.0
        expected_pipeline_share = (
            0.0
            if served == 0
            else parsed["pipeline_served_methanol_10kt"] / served * 100.0
        )
        if not _close(parsed["demand_met_pct"], expected_demand_met):
            raise ValueError(f"Figure 4 demand_met_pct does not agree at row {index}")
        if not _close(parsed["pipeline_share_pct"], expected_pipeline_share):
            raise ValueError(f"Figure 4 pipeline_share_pct does not agree at row {index}")
        records.append({"scenario": scenario, "tier": tier, "year": year, "region": region, **parsed})

    tier_year_combinations = sorted({(str(record["tier"]), int(record["year"])) for record in records})
    if len(tier_year_combinations) != 1:
        raise ValueError(
            "Figure 4 carrier must contain exactly one tier/year combination: "
            f"{tier_year_combinations}"
        )
    region_order = {region: index for index, region in enumerate(FIGURE_04_REGIONS)}
    records.sort(
        key=lambda record: (
            _scenario_key(str(record["scenario"])),
            str(record["tier"]),
            int(record["year"]),
            region_order.get(str(record["region"]), len(region_order)),
            str(record["region"]),
        )
    )
    scenarios = sorted({str(record["scenario"]) for record in records}, key=_scenario_key)
    regions = [region for region in FIGURE_04_REGIONS if region in {str(record["region"]) for record in records}]
    regions.extend(
        sorted(
            {str(record["region"]) for record in records} - set(regions),
            key=lambda value: value,
        )
    )
    by_key = {(str(record["scenario"]), str(record["region"])): record for record in records}

    demand_met = [
        [float(by_key[(scenario, region)]["demand_met_pct"]) for region in regions]
        for scenario in scenarios
    ]
    pipeline_share = [
        [float(by_key[(scenario, region)]["pipeline_share_pct"]) for region in regions]
        for scenario in scenarios
    ]
    regional_totals = {
        region: {
            field: math.fsum(
                float(record[field])
                for record in records
                if str(record["region"]) == region
            )
            for field in (
                "served_methanol_10kt",
                "unserved_methanol_10kt",
                "local_direct_methanol_10kt",
                "pipeline_served_methanol_10kt",
            )
        }
        for region in regions
    }

    _configure_plot()
    fig, axes = plt.subplots(2, 2, figsize=(15.0, 10.2), gridspec_kw={"height_ratios": (1.0, 1.15)})
    heatmaps = ((axes[0, 0], demand_met, "Demand met (%)", "#1D4ED8"), (axes[0, 1], pipeline_share, "Pipeline share of served (%)", "#15803D"))
    for axis, matrix, title, color in heatmaps:
        image = axis.imshow(matrix, aspect="auto", vmin=0, vmax=100, cmap="Blues" if color == "#1D4ED8" else "Greens")
        axis.set_xticks(list(range(len(regions))))
        axis.set_xticklabels(regions)
        axis.set_yticks(list(range(len(scenarios))))
        axis.set_yticklabels(scenarios)
        axis.set_xlabel("Region")
        axis.set_ylabel("Scenario")
        axis.set_title(title, loc="left", weight="bold")
        for row_index, values in enumerate(matrix):
            for column_index, value in enumerate(values):
                axis.text(
                    column_index,
                    row_index,
                    f"{value:.0f}",
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="white" if value >= 58 else FIGURE_TEXT,
                )
        fig.colorbar(image, ax=axis, fraction=0.046, pad=0.04, label="Percent")

    index_values = list(range(len(regions)))
    served_values = [regional_totals[region]["served_methanol_10kt"] for region in regions]
    unserved_values = [regional_totals[region]["unserved_methanol_10kt"] for region in regions]
    axes[1, 0].bar(index_values, served_values, color=FIGURE_BLUE, label="Served")
    axes[1, 0].bar(index_values, unserved_values, bottom=served_values, color="#F4B183", label="Unserved")
    axes[1, 0].set_xticks(index_values)
    axes[1, 0].set_xticklabels(regions)
    axes[1, 0].set_ylabel("Methanol (10 kt)")
    axes[1, 0].set_title("Regional served and unserved account", loc="left", weight="bold")
    axes[1, 0].legend(frameon=False, ncol=2)
    axes[1, 0].grid(axis="y", color="#E5E7EB", linewidth=0.5)
    axes[1, 0].set_axisbelow(True)

    local_values = [regional_totals[region]["local_direct_methanol_10kt"] for region in regions]
    pipeline_values = [regional_totals[region]["pipeline_served_methanol_10kt"] for region in regions]
    axes[1, 1].bar(index_values, local_values, color="#93C5FD", label="Local/direct")
    axes[1, 1].bar(index_values, pipeline_values, bottom=local_values, color=FIGURE_GREEN, label="Pipeline")
    axes[1, 1].set_xticks(index_values)
    axes[1, 1].set_xticklabels(regions)
    axes[1, 1].set_ylabel("Methanol (10 kt)")
    axes[1, 1].set_title("Regional service composition", loc="left", weight="bold")
    axes[1, 1].legend(frameon=False, ncol=2)
    axes[1, 1].grid(axis="y", color="#E5E7EB", linewidth=0.5)
    axes[1, 1].set_axisbelow(True)
    fig.suptitle(
        "Figure 4 | Regional service accounts across demand scenarios",
        color=FIGURE_TEXT,
        weight="bold",
        y=0.98,
    )
    fig.text(
        0.5,
        0.015,
        "Mid-tier 2060 regional aggregates; served and unserved values are model-derived accounts, not physical access claims.",
        ha="center",
        color=FIGURE_MUTED,
        fontsize=8,
    )
    fig.tight_layout(rect=(0.02, 0.04, 0.98, 0.95))
    _save_figure(fig, Path(output_path))
    plt.close(fig)
    return _metadata(
        input_path,
        output_path,
        rows,
        {
            "demand_met_heatmap": len(records),
            "pipeline_share_heatmap": len(records),
            "served_unserved_bars": len(regions),
            "local_pipeline_bars": len(regions),
        },
        scenarios=scenarios,
        regions=regions,
        tier_year_combinations=[
            {"tier": tier, "year": year} for tier, year in tier_year_combinations
        ],
        regional_totals=regional_totals,
        account_closure_validated=True,
    )


def build_figure_04(input_path: Path, output_path: Path) -> dict[str, object]:
    """Build the regional/scenario Figure 4 account comparison."""

    rows = _read_exact_rows(Path(input_path), FIGURE_04_COLUMNS)
    return _plot_figure_04(rows, Path(input_path), Path(output_path))


FIGURE_05_COLUMNS = (
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
)
FIGURE_05_METRICS = ("capacity_relaxation_gain_mt_y", "fixed_connector_gain_mt_y")


def _bool(value: str, *, field: str, row_index: int) -> bool:
    normalized = str(value).strip().casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"malformed boolean field {field} at row {row_index}")


def _plot_figure_05(
    rows: list[dict[str, str]], input_path: Path, output_path: Path
) -> dict[str, object]:
    grouped: dict[tuple[str, int], dict[str, dict[str, object]]] = {}
    for index, row in enumerate(rows, start=2):
        panel = _text(row["panel"], field="panel", row_index=index)
        if panel != "c":
            raise ValueError(f"Figure 5 public carrier must use panel c at row {index}")
        scenario = _text(row["scenario"], field="scenario", row_index=index)
        year = _year(row["year"], row_index=index)
        metric = _text(row["metric"], field="metric", row_index=index)
        if metric not in FIGURE_05_METRICS:
            raise ValueError(f"unknown Figure 5 metric at row {index}: {metric}")
        unit = _text(row["unit"], field="unit", row_index=index)
        source_type = _text(row["source_type"], field="source_type", row_index=index)
        style = _text(row["style"], field="style", row_index=index)
        marker = _text(row["marker"], field="marker", row_index=index)
        value = _nonnegative_number(row["value"], field="value", row_index=index)
        capacity_gain = _nonnegative_number(
            row["capacity_relaxation_gain_mt_y"],
            field="capacity_relaxation_gain_mt_y",
            row_index=index,
        )
        connector_gain = _nonnegative_number(
            row["connector_gain_mt_y"], field="connector_gain_mt_y", row_index=index
        )
        reaches_connector = _bool(
            row["capacity_reaches_connector"], field="capacity_reaches_connector", row_index=index
        )
        expected_value = capacity_gain if metric == "capacity_relaxation_gain_mt_y" else connector_gain
        if not _close(value, expected_value):
            raise ValueError(f"Figure 5 metric value does not agree with explicit gain at row {index}")
        key = (scenario, year)
        if key not in grouped:
            grouped[key] = {}
        if metric in grouped[key]:
            raise ValueError(f"duplicate Figure 5 metric row at row {index}: {key}, {metric}")
        grouped[key][metric] = {
            "scenario": scenario,
            "year": year,
            "metric": metric,
            "value": value,
            "capacity_gain": capacity_gain,
            "connector_gain": connector_gain,
            "reaches_connector": reaches_connector,
            "unit": unit,
            "source_type": source_type,
            "style": style,
            "marker": marker,
        }

    records: list[dict[str, object]] = []
    for key in sorted(grouped, key=lambda item: (_scenario_key(item[0]), item[1])):
        pair = grouped[key]
        if set(pair) != set(FIGURE_05_METRICS):
            raise ValueError(f"Figure 5 scenario pair is incomplete: {key}")
        capacity = pair["capacity_relaxation_gain_mt_y"]
        connector = pair["fixed_connector_gain_mt_y"]
        if not _close(float(capacity["capacity_gain"]), float(connector["capacity_gain"])):
            raise ValueError(f"Figure 5 capacity gain pair disagrees: {key}")
        if not _close(float(capacity["connector_gain"]), float(connector["connector_gain"])):
            raise ValueError(f"Figure 5 connector gain pair disagrees: {key}")
        if bool(capacity["reaches_connector"]) != bool(connector["reaches_connector"]):
            raise ValueError(f"Figure 5 reach flag pair disagrees: {key}")
        reaches = float(capacity["capacity_gain"]) >= float(capacity["connector_gain"]) - 1e-6
        if bool(capacity["reaches_connector"]) != reaches:
            raise ValueError(f"Figure 5 reach flag does not agree with gains: {key}")
        records.append(
            {
                "scenario": key[0],
                "year": key[1],
                "capacity_gain": float(capacity["capacity_gain"]),
                "connector_gain": float(capacity["connector_gain"]),
                "reaches_connector": bool(capacity["reaches_connector"]),
            }
        )

    _configure_plot()
    fig, axis = plt.subplots(figsize=(12.8, 7.5))
    y_values = list(range(len(records)))
    for y_value, record in zip(y_values, records):
        capacity_gain = float(record["capacity_gain"])
        connector_gain = float(record["connector_gain"])
        axis.plot(
            (capacity_gain, connector_gain),
            (y_value, y_value),
            color="#98A2B3",
            linewidth=2.0,
            solid_capstyle="round",
            zorder=1,
        )
        axis.scatter(
            (capacity_gain,),
            (y_value,),
            s=54,
            facecolor="white",
            edgecolor="#667085",
            linewidth=1.2,
            marker="o",
            zorder=3,
        )
        axis.scatter(
            (connector_gain,),
            (y_value,),
            s=54,
            facecolor=FIGURE_ORANGE,
            edgecolor="white",
            linewidth=0.8,
            marker="s",
            zorder=3,
        )
    scenarios = [str(record["scenario"]) for record in records]
    axis.set_yticks(y_values)
    axis.set_yticklabels(scenarios)
    axis.invert_yaxis()
    max_gain = max(
        [float(record["capacity_gain"]) for record in records]
        + [float(record["connector_gain"]) for record in records],
        default=0.0,
    )
    axis.set_xlim(0, max(1.0, max_gain * 1.16))
    axis.set_xlabel("Service gain (Mt/y)")
    axis.set_ylabel("Scenario")
    axis.set_title("Capacity relaxation versus fixed-connector replay", loc="left", weight="bold")
    axis.grid(axis="x", color="#E5E7EB", linewidth=0.5)
    axis.set_axisbelow(True)
    axis.legend(
        handles=[
            Line2D([], [], marker="o", linestyle="", markerfacecolor="white", markeredgecolor="#667085", label="Capacity relaxation"),
            Line2D([], [], marker="s", linestyle="", markerfacecolor=FIGURE_ORANGE, markeredgecolor="white", label="Fixed connector"),
        ],
        frameon=False,
        ncol=2,
        loc="lower right",
    )
    fig.suptitle(
        "Figure 5 | Scenario service-gain dumbbells",
        color=FIGURE_TEXT,
        weight="bold",
        y=0.98,
    )
    fig.text(
        0.5,
        0.015,
        "Panel c aggregate counterfactuals; endpoints are validated against the explicit gain columns in the public carrier.",
        ha="center",
        color=FIGURE_MUTED,
        fontsize=8,
    )
    fig.tight_layout(rect=(0.04, 0.04, 0.98, 0.95))
    _save_figure(fig, Path(output_path))
    plt.close(fig)
    return _metadata(
        input_path,
        output_path,
        rows,
        {"capacity_endpoints": len(records), "connector_endpoints": len(records), "dumbbell_pairs": len(records)},
        scenarios=scenarios,
        paired_gain_columns_validated=True,
    )


def build_figure_05(input_path: Path, output_path: Path) -> dict[str, object]:
    """Build the Figure 5 panel-c scenario gain dumbbells."""

    rows = _read_exact_rows(Path(input_path), FIGURE_05_COLUMNS)
    return _plot_figure_05(rows, Path(input_path), Path(output_path))


__all__ = ["build_figure_01", "build_figure_02", "build_figure_03", "build_figure_04", "build_figure_05"]
