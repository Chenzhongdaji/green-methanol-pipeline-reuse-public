# Headline claim expectations dictionary

`qa/expected/headline_claims.csv` contains the three release-level checks used
by the portable reproduction runner.

Licence class: author-generated aggregate data (CC BY 4.0).

| Column | Definition | Unit or codes | Missing-value policy | Derivation | Related panel |
| --- | --- | --- | --- | --- | --- |
| claim_id | Stable check identifier for a bounded headline quantity. | strict_pipeline_service_gap, no_terminal_gap, mapped_unserved_gap | blank forbidden | contract transcription from the release specification | terminal account checks |
| scenario_scope | Pooled scenario and year denominator. | S1-S8; mid; 2060 | blank forbidden | contract transcription | terminal account checks |
| metric | Quantity type used in the comparison. | gap | blank forbidden | metric-contract transcription | terminal account checks |
| expected_value | Rounded manuscript headline value. | percent or percentage points | blank forbidden | expected-value transcription; recomputed for verification | terminal account checks |
| unit | Display unit for the expected value. | percent or percentage_points | blank forbidden | display-metadata transcription | terminal account checks |
| tolerance | Absolute comparison tolerance. | percentage points | blank forbidden | reproduction-contract transcription | terminal account checks |
| evidence_boundary | Boundary statement for interpretation. | text | blank forbidden | evidence-boundary annotation | terminal account checks |

Values are recomputed from the released aggregate account rather than treated
as input observations.
