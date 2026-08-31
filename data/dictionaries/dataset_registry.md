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

The five seed rows are author-generated aggregate figure-source carriers and
are covered by the repository's explicit CC BY 4.0 data grant. Their hashes
are current worktree values; later staging and output checks must verify them
again before release.
