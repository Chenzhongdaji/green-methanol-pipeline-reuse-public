# Figure 4 regional aggregate dictionary

`figures/source_data/figure-04.csv` is a regional account subset for mid-demand
2060 across S1-S8. It deliberately contains region aggregates only and omits
city, refinery-proxy, node, coordinate and route fields.

| Column | Definition | Unit or codes |
| --- | --- | --- |
| scenario | Frozen demand scenario. | `S1` ... `S8` |
| tier | Demand tier. | `mid` |
| year | Model year. | integer year |
| region | Regional accounting group. | `NC`, `NE`, `EC`, `CC`, `SC`, `SW`, `NW` |
| demand_methanol_10kt | Regional demand. | 10 kt/y |
| local_direct_methanol_10kt | Same-city/direct service component. | 10 kt/y |
| pipeline_served_methanol_10kt | Pipeline service component. | 10 kt/y |
| served_methanol_10kt | Local plus pipeline served amount. | 10 kt/y |
| unserved_methanol_10kt | Residual demand after served amount. | 10 kt/y |
| demand_met_pct | Served share of regional demand. | percent |
| pipeline_share_pct | Pipeline share of served demand. | percent |

Missing values are not permitted; zero denotes an observed/modelled zero in the
aggregate table, not an unavailable datum. The table is model-derived and does
not establish trunk access or physical facility connections. Related panel:
Figure 4 panel c (regional heatmap aggregate).
