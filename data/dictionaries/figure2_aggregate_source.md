# Figure 2 partial aggregate-source dictionary

`data/author_derived/figure2_aggregate_source.csv` is a partial, editable
carrier for the quantitative parts of current rev03 Figure 2. It releases
safe aggregates for panels a--d and f--h. Panel e is represented by one
non-quantitative status row because the underlying reference map is
restricted; no map payload is redistributed.

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
| panel | Current Figure 2 panel represented by the row. | a--h | blank forbidden | panel-contract assignment | Figure 2 |
| record_type | Aggregate record family. | trajectory, scenario_account, gap_decomposition, counterfactual_relaxation, service_mode_account, scenario_point, strict_pipeline_account, strict_quantity_placement_2x2, strict_quantity_placement_effect, status | blank forbidden | controlled vocabulary assignment | Figure 2 a--h |
| scenario | Scenario or pooled scope. | S1--S8, S1-S8, or all for the map-status row | blank forbidden | source-scope transcription | Figure 2 a--h |
| tier | Demand tier for quantitative rows. | mid; all for the map-status row | blank forbidden | source-scope transcription | Figure 2 a--h |
| year | Model year or status reference year. | 2025--2060 or 2060 | blank forbidden | source-scope transcription | Figure 2 a--h |
| metric | Quantity represented by `value`. | controlled metric vocabulary below | blank forbidden | metric selection or aggregate transform | Figure 2 a--h |
| value | Aggregate value, or the literal `unavailable` for panel e. | percent, percentage points, 10 kt/y, or status code | blank forbidden; zero is a modelled zero | source transcription or documented transformation | Figure 2 a--h |
| unit | Display unit for `value`. | %, percentage points, 10 kt/y, or status | blank forbidden | unit assignment | Figure 2 a--h |
| source_boundary | Short, repository-safe provenance and interpretation boundary. | text; no machine-local path | blank forbidden | evidence-boundary annotation | Figure 2 a--h |
| variant | Display or source variant used to disambiguate repeated metrics. | dynamic_v08, baseline, local_co_location, strict_pipeline, terminal_account, strict_quantity_placement_2x2:<cell>, strict_quantity_placement_effect, restricted_map | blank forbidden | variant assignment | Figure 2 d, f, h |

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
- Panel e uses `metric=map_status`, `value=unavailable`,
  `source_boundary=restricted-map-not-released`; it is a release-status
  record, not a map substitute.

The carrier contains no map payload or exact network/location records. It is
model-derived aggregate evidence, not an observation, forecast, engineering
quotation, or proof of physical trunk access.
