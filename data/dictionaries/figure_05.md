# Figure 5 aggregate service-gain dictionary

`figures/source_data/figure-05.csv` releases only panel c's scenario-level
capacity and fixed-connector service gains. Candidate IDs, link names,
directions, coordinates and network-edge locators were removed after a
column-level review.

| Column | Definition | Unit or codes |
| --- | --- | --- |
| panel | Figure panel. | `c` |
| scenario | Frozen demand scenario. | `S1` ... `S8` |
| year | Model year. | 2060 |
| metric | Counterfactual service-gain metric. | `capacity_relaxation_gain_mt_y`, `fixed_connector_gain_mt_y` |
| value | Metric value. | Mt/y |
| unit | Display unit. | `Mt/y` |
| source_type | Aggregate audit class. | text |
| style | Display style metadata. | text |
| marker | Display marker metadata. | text |
| capacity_relaxation_gain_mt_y | Capacity-only counterfactual gain repeated for paired display rows. | Mt/y |
| connector_gain_mt_y | Fixed aggregate connector replay gain repeated for paired display rows. | Mt/y |
| capacity_reaches_connector | Whether the capacity-only counterfactual reaches the fixed replay in the source audit. | boolean |

Missing values are not permitted. These are model counterfactual aggregates,
not forecasts, engineering quotations or evidence that a named physical link
is approved. Related panel: Figure 5 panel c.
