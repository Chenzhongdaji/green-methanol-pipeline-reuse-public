# Public-source register dictionary

`data/public_sources.csv` is a metadata register. It records provenance and
use boundaries; it does not grant redistribution rights for linked material.

| Column | Definition | Unit or codes | Missing-value policy | Derivation | Related panel |
| --- | --- | --- | --- | --- | --- |
| source_id | Stable row identifier unique within the register. | text | blank forbidden | metadata transcription from the release manifest | release inventory |
| title | Source title or concise title of an author-derived aggregate. | text | blank forbidden | metadata transcription | release inventory |
| provider | Issuing body or author provenance. | text | blank forbidden | metadata transcription | release inventory |
| source_type | Evidence class assigned to the source. | `public source`, `engineering source`, or `author-generated aggregate` | blank forbidden | controlled vocabulary assignment | release inventory |
| stable_url_or_doi | Stable locator used to identify the evidence. | URL or DOI | blank forbidden | metadata transcription and locator review | release inventory |
| version_or_publication_date | Publication, release, or aggregate-calculation date. | ISO date or version text | blank forbidden | metadata transcription | release inventory |
| access_date | Date on which source metadata was checked. | ISO date | blank forbidden | metadata transcription | release inventory |
| used_for | Parameter, boundary, or screening use in this release. | text | blank forbidden | evidence-use annotation | release inventory |
| evidence_boundary | What the evidence supports and the limit of that support. | text | blank forbidden | evidence-boundary annotation | release inventory |
| redistribution_status | Whether payload or metadata is redistributed. | `Metadata only; source payload not redistributed` or `Aggregate value only; no third-party raw payload` | blank forbidden | rights review annotation | release inventory |
| licence_or_rights_status | Rights status for third-party or author-generated material. | text | blank forbidden | rights review annotation | release inventory |
| notes | Additional traceability or derivation note. | text | blank forbidden | metadata transcription | release inventory |

An open URL is not treated as an open licence. Third-party rows therefore
remain metadata-only unless source-specific redistribution rights are verified.
