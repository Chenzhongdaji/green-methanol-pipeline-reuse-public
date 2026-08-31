# Figure 2 visual review

Review target: `figures/figure-02e.png`, generated from the public 494-row
carrier with the Figure 2e builder.

## Checks

- Legibility: PASS. The coordinate-based network occupies the main panel; the
  light-grey existing segments and orange model-called overlay remain
  distinguishable, and the legend is readable at the rendered resolution.
- Network layers: PASS. The image shows all 140 directed existing-network
  records and the contrasting 11 model-called task records. The two network
  records whose design throughput is unknown remain light grey and are not
  treated as zero.
- Coverage summary: PASS. The right-hand inset is a compact 29-row province
  demand-coverage bar summary using carrier province labels and values; no
  province polygons were invented.
- Basemap claim: PASS. The visible note reads exactly
  `Analytical coordinates; no official basemap`.
- Determinism: PASS. Repeated Figure 2e builds produced the same PNG SHA-256;
  the sibling PDF was generated in the same run.

## Limitations

The x/y fields are analytical coordinate pairs supplied by the carrier, not a
georeferenced or official map. Line width is scaled only for the 138 available
design-throughput values; the two explicitly unknown values use a thin neutral
line so unknown is not encoded as zero. The inset is a labelled bar summary,
not a geographic province map.
