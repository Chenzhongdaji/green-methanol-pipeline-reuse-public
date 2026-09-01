# Figure panel map dictionary

`figures/panel_map.csv` records the public source carrier and field dictionary
for each released panel group.

The mapped aggregate carriers are labelled as author-generated aggregate data
(CC BY 4.0); this map metadata does not license third-party sources.

| Column | Definition | Unit or codes | Missing-value policy | Derivation | Related panel |
| --- | --- | --- | --- | --- | --- |
| figure | Manuscript figure label. | Figure 1-Figure 5 | blank forbidden | panel-map transcription | panel map |
| panel | Panel selector; a-d,f-h and e are separate Figure 2 carrier groups. | text or all | blank forbidden | panel-map transcription | panel map |
| status | Closed workflow status. | aggregate-only or not-run | blank forbidden | release-status assignment | panel map |
| source_data | Repository-relative CSV for the released panel carrier. | POSIX path | blank forbidden for aggregate-only rows | source-carrier pairing review | panel map |
| dictionary | Repository-relative field dictionary for the source CSV. | POSIX path | blank forbidden for aggregate-only rows | dictionary pairing review | panel map |
| reason | Evidence boundary and reproduction relationship. | text | blank forbidden | evidence-boundary annotation | panel map |

Figure 2 panels a-d and f-h use the direct executable carrier
`data/figure_source/figure-02.csv` together with
`data/dictionaries/figure_02.md`; the output registry identifies it as
`figure-02-source-real`. Figure 2e uses the same direct executable carrier,
dictionary and registry entry. The author-derived aggregate carrier
`data/author_derived/figure2_aggregate_source.csv` is supplementary derived
evidence only and is not a direct builder input. The full registry workflow
consumes the direct carrier and writes both `figures/figure-02e.png` and
`figures/figure-02e.pdf`.
