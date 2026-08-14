# Strict terminal-gap aggregate dictionary

`data/author_derived/terminal_gap_aggregate.csv` is a single pooled account
used to recompute the three public headline checks. It is an author-generated
aggregate and contains no facility identifiers, trunk links, coordinates or
physical edge records.

| Column | Definition | Unit or codes |
| --- | --- | --- |
| scenario_scope | Frozen pooled denominator across S1-S8, mid tier, 2060. | text |
| tier | Demand tier. | `mid` |
| year | Model year. | integer year |
| aggregation | Pooled denominator rule. | `demand_weighted` |
| demand_10kt | Total city demand in the pooled account. | 10 kt/y |
| pipeline_served_10kt | Strict pipeline-served demand after the declared evidence contract. | 10 kt/y |
| no_terminal_unserved_10kt | Demand lacking a uniquely mapped terminal record. | 10 kt/y |
| mapped_unserved_10kt | Demand with a mapped terminal but no strict pipeline service. | 10 kt/y |
| account_status | Mass-balance closure state. | `closed` |
| scope_note | Interpretation boundary and additive-account note. | text |

Missing values are not allowed. The three gap percentages are calculated as
the corresponding numerator divided by `demand_10kt` and multiplied by 100.
