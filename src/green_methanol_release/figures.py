"""Deterministic, public-carrier figure builders for the release package."""

from __future__ import annotations

import csv
import hashlib
import math
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


FIGURE_DPI = 150
FIGURE_FONT = "Microsoft YaHei"
FIGURE_TEXT = "#233044"
FIGURE_MUTED = "#667085"
FIGURE_GRID = "#D0D5DD"
FIGURE_BLUE = "#1D4ED8"
FIGURE_ORANGE = "#D97706"
FIGURE_GREEN = "#15803D"

_CSV_ENCODING = "utf-8-sig"


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
    path = Path(path)
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
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _save_figure(fig: plt.Figure, output: Path, *, pdf: bool = False) -> None:
    output = Path(output)
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


__all__ = ["build_figure_02"]
