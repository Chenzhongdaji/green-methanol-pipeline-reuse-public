# Figure 1 aggregate framework dictionary

`figures/source_data/figure-01.csv` is the editable conceptual workflow carrier
for Figure 1. It contains labels and stage links only; it is not a network
registry and cannot reconstruct physical nodes, edges or facility mappings.

| Column | Definition | Unit or codes |
| --- | --- | --- |
| element_id | Stable conceptual stage identifier. | text |
| element_type | Workflow lane. | `evidence`, `allocation`, `output` |
| label | Short display label. | text |
| detail | Display detail repeated for editing convenience. | text |
| source_class | Evidence class used in the conceptual diagram. | `model_output` |
| target | Next conceptual stage label when present. | text or blank |

Missing values are blank only for terminal conceptual stages. Derivation is a
manual transcription of the approved framework source carrier; no quantitative
claim is computed from this table. Related panel: Figure 1 (all conceptual
panels).
