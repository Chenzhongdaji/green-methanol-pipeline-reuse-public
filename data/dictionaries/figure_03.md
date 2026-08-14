# Figure 3 aggregate C1 dictionary

`figures/source_data/figure-03.csv` contains scenario-level transport
aggregates for the Figure 3 C1 panel. It has no task, demand-node, station,
edge, coordinate, or route identifier.

| Column | Definition | Unit or codes | Missing-value policy | Derivation | Related panel |
| --- | --- | --- | --- | --- | --- |
| scenario | Frozen demand scenario. | S1-S8 | blank forbidden | scenario-label transcription | Figure 3 (aggregate C1) |
| year | Model year. | integer year | blank forbidden | model-output transcription | Figure 3 (aggregate C1) |
| distance_km | Flow-weighted pipeline task distance for the scenario. | km | blank forbidden | aggregate calculation from approved C1 carrier | Figure 3 (aggregate C1) |
| pipeline_tonne_km | Aggregate pipeline transport task. | tonne-km | blank forbidden | aggregate calculation from approved C1 carrier | Figure 3 (aggregate C1) |
| delivered_tonnes | Aggregate pipeline-delivered methanol. | tonnes | blank forbidden | aggregate calculation from approved C1 carrier | Figure 3 (aggregate C1) |

These are model-derived aggregates, not observations or a claim that every
physical segment is qualified.
