# Figure 4 regional aggregate dictionary

`figures/source_data/figure-04.csv` is a regional account subset for mid-demand
2060 across S1-S8. It deliberately contains region aggregates only and omits
city, refinery-proxy, node, coordinate, and route fields.

| Column | Definition | Unit or codes | Missing-value policy | Derivation | Related panel |
| --- | --- | --- | --- | --- | --- |
| scenario | Frozen demand scenario. | S1-S8 | blank forbidden | scenario-label transcription | Figure 4 panel c |
| tier | Demand tier. | mid | blank forbidden | scenario-contract transcription | Figure 4 panel c |
| year | Model year. | 2060 | blank forbidden | model-output transcription | Figure 4 panel c |
| region | Regional accounting group. | NC, NE, EC, CC, SC, SW, NW | blank forbidden | regional aggregation label | Figure 4 panel c |
| demand_methanol_10kt | Regional methanol demand. | 10 kt/y | blank forbidden; zero is a modelled zero | regional sum from approved aggregate carrier | Figure 4 panel c |
| local_direct_methanol_10kt | Same-city or direct-service component. | 10 kt/y | blank forbidden; zero is a modelled zero | regional sum from approved aggregate carrier | Figure 4 panel c |
| pipeline_served_methanol_10kt | Pipeline service component. | 10 kt/y | blank forbidden; zero is a modelled zero | regional sum from approved aggregate carrier | Figure 4 panel c |
| served_methanol_10kt | Local plus pipeline served amount. | 10 kt/y | blank forbidden; zero is a modelled zero | aggregate account calculation | Figure 4 panel c |
| unserved_methanol_10kt | Residual demand after served amount. | 10 kt/y | blank forbidden; zero is a modelled zero | aggregate account calculation | Figure 4 panel c |
| demand_met_pct | Served share of regional demand. | percent | blank forbidden | percentage calculation from aggregate account | Figure 4 panel c |
| pipeline_share_pct | Pipeline share of served demand. | percent | blank forbidden | percentage calculation from aggregate account | Figure 4 panel c |

The table is model-derived and does not establish trunk access or physical
facility connections.
