# Figure panel map dictionary

`figures/panel_map.csv` records which panels have safe aggregate source data in
this release and which are deliberately withheld.

| Column | Definition | Unit or codes | Missing-value policy | Derivation | Related panel |
| --- | --- | --- | --- | --- | --- |
| figure | Manuscript figure label. | Figure 1-Figure 5 | blank forbidden | panel-map transcription | panel map |
| panel | Panel selector; all denotes conceptual or aggregate scope. | text or all | blank forbidden | panel-map transcription | panel map |
| status | Closed workflow status. | aggregate-only or not-run | blank forbidden | release-status assignment | panel map |
| source_data | Repository-relative CSV when a panel is released. | POSIX path or not_applicable | explicit not_applicable allowed for withheld panels | source-carrier pairing review | panel map |
| dictionary | Repository-relative field dictionary for the source CSV. | POSIX path or not_applicable | explicit not_applicable allowed for withheld panels | dictionary pairing review | panel map |
| reason | Evidence boundary or withholding reason. | text | blank forbidden | evidence-boundary annotation | panel map |

Figure 2 is explicitly `not-run` because its map source and formal review are not
cleared for public release. Blank source and dictionary fields are intentional
only for that withheld row.
