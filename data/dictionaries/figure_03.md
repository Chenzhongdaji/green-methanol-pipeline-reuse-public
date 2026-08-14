# Figure 3 aggregate C1 dictionary

`figures/source_data/figure-03.csv` contains scenario-level transport
aggregates for the Figure 3 C1 panel. It has no task, demand-node, station,
edge, coordinate or route identifier and therefore cannot reconstruct directed
topology or facility connections.

| Column | Definition | Unit or codes |
| --- | --- | --- |
| scenario | Frozen demand scenario. | `S1` ... `S8` |
| year | Model year. | integer year |
| distance_km | Flow-weighted pipeline task distance for the scenario. | km |
| pipeline_tonne_km | Aggregate pipeline transport task. | tonne-km |
| delivered_tonnes | Aggregate pipeline-delivered methanol. | tonnes |

Missing values are not permitted. Values are model-derived aggregates from the
approved C1 output carrier, not observations or a claim that every physical
segment is qualified. Related panel: Figure 3 (aggregate C1 panel).
