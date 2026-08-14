# Headline claim expectations dictionary

`qa/expected/headline_claims.csv` contains the three release-level checks used
by the portable reproduction runner.

| Column | Definition | Unit or codes |
| --- | --- | --- |
| claim_id | Stable check identifier; the strict gap is split into two evidence-boundary components. | text |
| scenario_scope | Pooled S1-S8 mid-demand 2060 denominator. | text |
| metric | Quantity type used in the comparison. | `gap` |
| expected_value | Rounded manuscript headline value. | percent or percentage points |
| unit | Display unit for the expected value. | `percent`, `percentage_points` |
| tolerance | Absolute comparison tolerance used by the runner. | percentage points |
| evidence_boundary | Boundary statement for interpretation; not an observation or engineering quote. | text |

Missing values are not permitted. Values are recomputed from the released
aggregate account rather than treated as input observations.
