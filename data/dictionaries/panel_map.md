# Figure panel map dictionary

`figures/panel_map.csv` records which panels have safe aggregate source data in
this release and which are deliberately withheld.

The mapped aggregate carriers are labelled as author-generated aggregate data
(CC BY 4.0); this map metadata does not license third-party sources.

| Column | Definition | Unit or codes | Missing-value policy | Derivation | Related panel |
| --- | --- | --- | --- | --- | --- |
| figure | Manuscript figure label. | Figure 1-Figure 5 | blank forbidden | panel-map transcription | panel map |
| panel | Panel selector; a-d,f-h denotes the released quantitative subset. | text or all | blank forbidden | panel-map transcription | panel map |
| status | Closed workflow status. | aggregate-only or not-run | blank forbidden | release-status assignment | panel map |
| source_data | Repository-relative CSV when a panel is released. | POSIX path or blank | blank only for withheld rows | source-carrier pairing review | panel map |
| dictionary | Repository-relative field dictionary for the source CSV. | POSIX path or blank | blank only for withheld rows | dictionary pairing review | panel map |
| reason | Evidence boundary or withholding reason. | text | blank forbidden | evidence-boundary annotation | panel map |

Figure 2 has a partial `aggregate-only` carrier for panels a-d and f-h. Panel e
is represented only by a `restricted-map-not-released` status row; no map
payload is released. The Figure 2 dictionary records the upstream selection
and transformation boundary, and does not present the upstream Figure 3 file
as a current Figure 2 source.
