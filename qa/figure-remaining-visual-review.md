# Visual review: remaining public figures

Visual inspection was performed on the generated PNGs at their native raster
layout after the real builders completed. The review checks legibility,
encoding fidelity, clipping/overlap, and the evidence boundary of each public
carrier.

## Figure 1

- Legibility: PASS. The six workflow lanes, node labels, arrow directions and
  legend remain readable at the rendered size.
- Encoding fidelity: PASS. Each carrier row is rendered as one labelled node;
  non-empty `target` values become links to the matching label. The footer
  explicitly states that no topology or quantitative result is added.
- Clipping/overlap: PASS. Node boxes, lane headings, legend and footer are
  inside the canvas; the narrowest labels are wrapped within their boxes.
- Limitations: This is a conceptual aggregate workflow, not a geographic
  network or facility diagram. Labels with no target are terminal nodes.

## Figure 3

- Legibility: PASS. Scenario labels S1-S8, distance and delivered-volume axes,
  bubble-size legend, and tonne-kilometre bars are readable.
- Encoding fidelity: PASS. Horizontal position uses `distance_km`, vertical
  position uses `delivered_tonnes`, bubble area uses `pipeline_tonne_km`, and
  the companion bars use the same pipeline task field.
- Clipping/overlap: PASS. All eight bubbles and labels are visible; the two
  panels and bottom evidence note have no visible clipping or overlap.
- Limitations: Values are scenario-level model aggregates. Bubble area and
  bar axes use display-scale conversions (million/billion) while retaining the
  carrier fields; this does not establish qualified physical routes.

## Figure 4

- Legibility: PASS. Region codes, S1-S8 scenario labels, percentage annotations,
  colorbars, and served/unserved legends are readable.
- Encoding fidelity: PASS. The upper panels use the carrier's `demand_met_pct`
  and `pipeline_share_pct`; lower panels show regional served/unserved and
  local/direct-pipeline account components from the numeric fields.
- Clipping/overlap: PASS. Heatmap annotations, colorbars, stacked bars, axes,
  legends and footer are contained within the four-panel layout.
- Limitations: The panel is a mid-tier 2060 regional account comparison. It
  contains no city, refinery-proxy, node, coordinate or route identifiers and
  does not establish trunk access or physical facility connections.

## Figure 5

- Legibility: PASS. S1-S8 labels, endpoint markers, connecting lines, x-axis
  units and the two-entry legend are readable.
- Encoding fidelity: PASS. Hollow circles encode capacity-relaxation gains,
  orange squares encode fixed-connector gains, and each line connects the
  paired values after validation against the explicit gain columns.
- Clipping/overlap: PASS. All eight dumbbell pairs are visible, including the
  zero-capacity endpoints at the left boundary; legend and footer do not cover
  data marks.
- Limitations: These are panel-c aggregate counterfactual service gains, not
  engineering quotes, forecasts, connector identifiers, or evidence that a
  named physical link is approved.
