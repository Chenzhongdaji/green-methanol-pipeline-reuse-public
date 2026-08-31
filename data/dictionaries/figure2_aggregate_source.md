# Figure 2 aggregate-source dictionary

`data/author_derived/figure2_aggregate_source.csv` is the author-derived
aggregate carrier for the quantitative parts of Figure 2 panels a--d and f--h.
Figure 2e has its own public row-level carrier at
`data/figure_source/figure-02.csv`, registered as `figure-02-source-real` and
documented in `data/dictionaries/figure_02.md`.

Licence class: author-generated aggregate data (CC BY 4.0).

The file named `fig03_dynamic_v08_source_data.csv` is an upstream Figure 3
dynamic-v08 aggregate source, not the current Figure 2 source file. Only its
panel-a, panel-b and panel-c aggregate fields are selected here. Panel a is
the served-share trajectory; panel b supplies the 2060 scenario account; and
panel c supplies the gap decomposition and the four S5--S8 counterfactual
gain rows labelled as Figure 2 panel d. The upstream panel-d province/map
rows are deliberately not copied. This selection and transformation prevents
an old Figure 3 file from being presented as a current Figure 2 source.

The f rows are demand-weighted service-mode accounts and scenario points
from `service_mode_summary.csv`. The display variants map to the upstream
variants `baseline_replay`, `free_all_positive_city_support` and
`free_all_positive_city_support_no_local_direct`, respectively. `baseline`,
`local_co_location` and `strict_pipeline` are display variants, not scenario
probabilities. The g
rows are the pooled terminal-gap account after removing machine-local
provenance fields; their values are cross-checked against the public
`terminal_gap_aggregate.csv`. The h rows are S1--S8, mid-tier, 2060
demand-weighted cells and effect annotations from `cross_2x2.csv`.

| Column | Definition | Unit or codes | Missing-value policy | Derivation | Related panel |
| --- | --- | --- | --- | --- | --- |
| panel | Current Figure 2 panel represented by the row. | a--d, f--h | blank forbidden | panel-contract assignment | Figure 2 |
| record_type | Aggregate record family. | trajectory, scenario_account, gap_decomposition, counterfactual_relaxation, service_mode_account, scenario_point, strict_pipeline_account, strict_quantity_placement_2x2, strict_quantity_placement_effect | blank forbidden | controlled vocabulary assignment | Figure 2 a--d, f--h |
| scenario | Scenario or pooled scope. | S1--S8 or S1-S8 | blank forbidden | source-scope transcription | Figure 2 a--d, f--h |
| tier | Demand tier for quantitative rows. | mid | blank forbidden | source-scope transcription | Figure 2 a--d, f--h |
| year | Model year. | 2025--2060 or 2060 | blank forbidden | source-scope transcription | Figure 2 a--d, f--h |
| metric | Quantity represented by `value`. | controlled metric vocabulary below | blank forbidden | metric selection or aggregate transform | Figure 2 a--h |
| value | Aggregate value. | percent, percentage points, 10 kt/y, or numeric display value | blank forbidden; zero is a modelled zero | source transcription or documented transformation | Figure 2 a--d, f--h |
| unit | Display unit for `value`. | %, percentage points, or 10 kt/y | blank forbidden | unit assignment | Figure 2 a--d, f--h |
| source_boundary | Short, repository-safe provenance and interpretation boundary. | text; no machine-local path | blank forbidden | evidence-boundary annotation | Figure 2 a--d, f--h |
| variant | Display or source variant used to disambiguate repeated metrics. | dynamic_v08, baseline, local_co_location, strict_pipeline, terminal_account, strict_quantity_placement_2x2:<cell>, strict_quantity_placement_effect | blank forbidden | variant assignment | Figure 2 d, f, h |

## Metric vocabulary and transforms

- Panel a uses `served_share_pct` directly from the upstream aggregate
  `demand_met_pct` field and retains three S5 `dynamic_demand_mt` callouts
  (2025, 2030 and 2060) converted from 10 kt/y to Mt.
- Panel b renames the upstream `supply_gap_pct` to
  `quantity_shortage_pct`; `served_pct` and `spatial_network_gap_pct` are
  retained as aggregate percentages.
- Panel c retains `direction_contribution_pct`,
  `capacity_contribution_pct` and `topology_access_residual_pct`. Panel d
  calculates each gain as one of
  `capacity_relaxed_service_10kt`, `direction_relaxed_service_10kt` or
  `both_relaxed_service_10kt` minus `baseline_service_10kt`, in 10 kt/y.
- Panel f calculates each service percentage as the selected service amount
  (`local_service_10kt`, `pipeline_delivered_10kt` or `unserved_10kt`)
  divided by the corresponding `demand_10kt` and multiplied by 100.
- Panel g calculates the pipeline-service share and the two additive terminal
  gap components from the pooled account denominator. The components are
  percentage points of pooled demand, not physical component assignments.
- Panel h demand-weights each cell and effect across the eight scenario rows;
  effect values are percentage-point differences of the unserved-demand
  cells.
The separate Figure 2e carrier is the source for the public analytical map
view. The Figure 2e builder uses its real carrier rows directly and writes
`figures/figure-02e.png` plus `figures/figure-02e.pdf`; the aggregate carrier
above is not substituted for those rows.

The carrier contains no map payload or exact network/location records. It is
model-derived aggregate evidence, not an observation, forecast, engineering
quotation, or proof of physical trunk access.
