# Figure 5 aggregate service-gain dictionary

`figures/source_data/figure-05.csv` releases only panel c's scenario-level
capacity and fixed-connector service gains. Candidate IDs, link names,
directions, coordinates, and network-edge locators are excluded.

Licence class: author-generated aggregate data (CC BY 4.0).

| Column | Definition | Unit or codes | Missing-value policy | Derivation | Related panel |
| --- | --- | --- | --- | --- | --- |
| panel | Figure panel identifier. | c | blank forbidden | panel-contract transcription | Figure 5 panel c |
| scenario | Frozen demand scenario. | S1-S8 | blank forbidden | scenario-label transcription | Figure 5 panel c |
| year | Model year. | 2060 | blank forbidden | model-output transcription | Figure 5 panel c |
| metric | Counterfactual service-gain metric. | capacity_relaxation_gain_mt_y or fixed_connector_gain_mt_y | blank forbidden | metric-label transcription | Figure 5 panel c |
| value | Metric value. | Mt/y | blank forbidden | aggregate counterfactual output transcription | Figure 5 panel c |
| unit | Display unit for the metric. | Mt/y | blank forbidden | display-metadata transcription | Figure 5 panel c |
| source_type | Aggregate audit class. | text | blank forbidden | evidence-class annotation | Figure 5 panel c |
| style | Display style metadata. | text | blank forbidden | figure-style transcription | Figure 5 panel c |
| marker | Display marker metadata. | text | blank forbidden | figure-style transcription | Figure 5 panel c |
| capacity_relaxation_gain_mt_y | Capacity-only counterfactual gain repeated for paired display rows. | Mt/y | blank forbidden | aggregate counterfactual calculation | Figure 5 panel c |
| connector_gain_mt_y | Fixed aggregate connector replay gain repeated for paired display rows. | Mt/y | blank forbidden | aggregate counterfactual calculation | Figure 5 panel c |
| capacity_reaches_connector | Whether capacity-only counterfactual reaches the fixed replay. | boolean | blank forbidden | comparison of paired counterfactual outputs | Figure 5 panel c |

These are model counterfactual aggregates, not forecasts, engineering quotes, or
evidence that a named physical link is approved.
