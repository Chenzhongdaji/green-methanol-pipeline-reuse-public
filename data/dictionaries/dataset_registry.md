# Dataset registry dictionary

`data/dataset_registry.csv` is the machine-readable map from a public
repository carrier to its provenance, rights boundary and manuscript use.
Paths are repository-relative POSIX paths. The registry is metadata only: a
path does not imply that the carrier has already been staged by a later
workflow task.

| Column | Definition | Missing-value policy |
| --- | --- | --- |
| dataset_id | Stable identifier used by output rows and staging. | Blank and duplicates forbidden. |
| public_path | Repository-relative path to the public carrier. | Blank, absolute, escaping, non-POSIX and excluded-directory paths forbidden. |
| role | Functional role of the carrier, such as a terminal figure-source carrier. | Blank forbidden. |
| origin | Provenance class, including author-generated aggregate data. | Blank forbidden. |
| access_route | How a clean checkout obtains the carrier. | Blank forbidden; repository-deposited author data may omit acquisition_command. |
| license | Licence or rights boundary applying to this carrier. | Blank forbidden; a repository grant is not inferred for third-party data. |
| sha256 | Lowercase SHA-256 digest of the staged carrier. | Empty is allowed before staging; otherwise exactly 64 lowercase hexadecimal characters. |
| acquisition_command | Reproducible acquisition command for data not already deposited. | Blank only for author-generated data already deposited in the repository. |
| processing_command | Command that creates this carrier from its declared upstream inputs. | Blank only for a terminal source-data carrier. |
| manuscript_uses | Figures, tables or claims that consume the carrier. | Blank forbidden. |
| source_relative_path | Path under the staging source root for a copy action. | Blank required for existing and acquire actions; otherwise repository-relative and safe. |
| stage_action | Staging disposition for this carrier. | Exactly `copy`, `existing` or `acquire`. |

The five seed rows are author-generated aggregate figure-source carriers. Each
`license=CC BY 4.0` value is supported only by the matching entry in the
repository `LICENSE-DATA` allowlist:

| dataset_id | allowlisted carrier |
| --- | --- |
| figure-01-source | `figures/source_data/figure-01.csv` |
| figure-02-aggregate-source | `data/author_derived/figure2_aggregate_source.csv` |
| figure-03-source | `figures/source_data/figure-03.csv` |
| figure-04-source | `figures/source_data/figure-04.csv` |
| figure-05-source | `figures/source_data/figure-05.csv` |

This mapping does not extend the data grant to any other carrier or to
third-party material. The listed hashes are current worktree values; later
staging and output checks must verify them again before release.

## Task 3B staged carrier extension

Task 3B adds 33 explicit author-generated/author-controlled reproduction
carriers with `stage_action=copy`. Their `sha256` values are computed from the
named source files before registration and are checked again at the destination
by the staging engine. These carriers are not added to the seed `CC BY 4.0`
allowlist; `author-controlled; no additional licence` preserves the verified
repository-rights boundary.

The `standard-map-gs2023-2767` row uses `stage_action=acquire` for the official
catalogue metadata record only. The copied JSON retains third-party and
not-relicensed terms. Official JPG/EPS payloads and any research-boundary SHP
are not deposited because redistribution permission is not confirmed.
