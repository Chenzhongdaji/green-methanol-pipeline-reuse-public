# Figure 2 public source-carrier dictionary

`data/figure_source/figure-02.csv` is the public row-level carrier for the
Figure 2 builder. It is registered as `figure-02-source-real` in
`data/dataset_registry.csv` and is consumed by the Figure 2 panel-e and summary
commands in `data/output_registry.csv`. The panel-e command writes the primary
PNG and the registered secondary PDF, so both outputs are covered by the full
reproduction report and checksum contract.

The carrier contains analytical coordinates and aggregate annotations needed
by the public plotting code. It does not assert official basemap geometry or
facility ownership. Values and labels are reproduced exactly from the reviewed
public carrier used by the release workflow.

| Column | Definition | Unit or codes | Missing-value policy | Derivation | Related panel |
| --- | --- | --- | --- | --- | --- |
| panel | Figure 2 panel selector. | a, b, c, d, e, f, g, h | blank forbidden | panel-contract assignment | Figure 2 |
| scenario | Scenario or pooled scenario scope. | S1, S2, ..., S8, or S1-S8 | blank forbidden | source-carrier transcription | Figure 2 |
| year | Model or display year. | 2025-2060 | blank forbidden | source-carrier transcription | Figure 2 |
| case | Record family used by the builder. | controlled case label | blank forbidden | source-carrier transcription | Figure 2 |
| metric | Quantity or annotation represented by the row. | controlled metric label | blank forbidden | source-carrier transcription | Figure 2 |
| value | Numeric value for the record. | numeric, percent, or percentage points | blank only for label-only annotations | source-carrier transcription | Figure 2 |
| unit | Display unit for the value. | %, percentage points, 10 kt/y, or label | blank forbidden | unit assignment | Figure 2 |
| denominator | Population or scope used for the value. | text | blank forbidden | denominator annotation | Figure 2 |
| source_type | Public carrier source class. | frozen aggregate or reviewed carrier class | blank forbidden | source-boundary assignment | Figure 2 |
| style | Rendering style consumed by the builder. | trajectory, bar, edge, point, or annotation style | blank forbidden | plotting contract | Figure 2 |
| x | Horizontal coordinate, category, or label. | numeric or text | blank allowed for records without an x coordinate | plotting contract | Figure 2 |
| y | Vertical coordinate or display value. | numeric or text | blank allowed for records without a y coordinate | plotting contract | Figure 2 |
| note | Human-readable evidence-boundary or plotting annotation. | text | blank allowed when no annotation is needed | source-carrier annotation | Figure 2 |

The release validator checks the exact header, UTF-8/LF encoding, public-column
boundary and row set before the full orchestrator runs the registered builders.
