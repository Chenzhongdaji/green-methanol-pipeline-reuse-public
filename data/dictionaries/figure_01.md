# Figure 1 aggregate framework dictionary

`figures/source_data/figure-01.csv` is the editable conceptual workflow
carrier for Figure 1. It contains labels and stage links only; it is not a
network registry and cannot reconstruct physical nodes, edges, or facilities.

Licence class: author-generated aggregate data (CC BY 4.0).

| Column | Definition | Unit or codes | Missing-value policy | Derivation | Related panel |
| --- | --- | --- | --- | --- | --- |
| element_id | Stable conceptual stage identifier. | text | blank forbidden | manual transcription of the approved framework carrier | Figure 1 (all) |
| element_type | Workflow lane assigned to the conceptual element. | evidence, allocation, output, transform, metric, decision | blank forbidden | controlled vocabulary assignment | Figure 1 (all) |
| label | Short display label. | text | blank forbidden | manual transcription | Figure 1 (all) |
| detail | Display detail repeated for editing convenience. | text | blank forbidden | manual transcription | Figure 1 (all) |
| source_class | Evidence class used in the conceptual diagram. | model_output or post_model_transform | blank forbidden | evidence-class annotation | Figure 1 (all) |
| target | Next conceptual stage label when present. | text or blank for terminal stage | blank for terminal stages | workflow-link transcription | Figure 1 (all) |

This conceptual carrier does not compute quantitative claims or expose topology.
