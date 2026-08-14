# Strict terminal-gap aggregate dictionary

`data/author_derived/terminal_gap_aggregate.csv` is a single pooled account
used to recompute the three public headline checks. It contains no facility
identifiers, trunk links, coordinates, or physical edge records.

Licence class: author-generated aggregate data (CC BY 4.0).

| Column | Definition | Unit or codes | Missing-value policy | Derivation | Related panel |
| --- | --- | --- | --- | --- | --- |
| scenario_scope | Frozen pooled denominator across S1-S8, mid tier, 2060. | S1-S8 pooled | blank forbidden | account-scope transcription | headline checks |
| tier | Demand tier. | mid | blank forbidden | account-scope transcription | headline checks |
| year | Model year. | 2060 | blank forbidden | account-scope transcription | headline checks |
| aggregation | Pooled denominator rule. | demand_weighted | blank forbidden | account-contract transcription | headline checks |
| demand_10kt | Total city demand in the pooled account. | 10 kt/y | blank forbidden | pooled sum from approved terminal account | headline checks |
| pipeline_served_10kt | Strict pipeline-served demand after the evidence contract. | 10 kt/y | blank forbidden | pooled sum from approved terminal account | headline checks |
| no_terminal_unserved_10kt | Demand lacking a uniquely mapped terminal record. | 10 kt/y | blank forbidden | pooled sum from approved terminal account | headline checks |
| mapped_unserved_10kt | Demand with a mapped terminal but no strict pipeline service. | 10 kt/y | blank forbidden | pooled sum from approved terminal account | headline checks |
| account_status | Mass-balance closure state. | closed | blank forbidden | account QA transcription | headline checks |
| scope_note | Interpretation boundary and additive-account note. | text | blank forbidden | evidence-boundary annotation | headline checks |

The three gap percentages are calculated as each numerator divided by
`demand_10kt` and multiplied by 100.
