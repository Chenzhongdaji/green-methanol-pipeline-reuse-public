# Figure panel map dictionary

`figures/panel_map.csv` records which figure panels have safe aggregate source
data in this release and which are deliberately withheld.

| Column | Definition | Unit or codes |
| --- | --- | --- |
| figure | Manuscript figure label. | `Figure 1` ... `Figure 5` |
| panel | Panel selector; `all` means the source is conceptual or aggregate for the mapped figure scope. | text |
| status | Closed workflow status. | `aggregate-only`, `not-run` |
| source_data | Repository-relative CSV when a panel is released. | POSIX path or blank |
| dictionary | Repository-relative field dictionary for the source CSV. | POSIX path or blank |
| reason | Evidence boundary or withholding reason. | text |

Figure 2 is explicitly `not-run` because the GS(2023)2767 map source and formal
map review are not cleared for public release. Blank fields are intentional for
withheld panels.
