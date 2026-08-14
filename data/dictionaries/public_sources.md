# Public-source register dictionary

public_sources.csv is a metadata register. It records where evidence came
from and how it was used; it is not a licence for the linked source.

| Field | Meaning |
| --- | --- |
| source_id | Stable row identifier; unique within this register. |
| title | Source title or concise title of an author-derived aggregate. |
| provider | Issuing body or author provenance. |
| source_type | public source, engineering source, or explicitly labelled author-generated aggregate. |
| stable_url_or_doi | Stable public URL or DOI used to locate the evidence. |
| version_or_publication_date | Publication, release, or aggregate-calculation date. |
| access_date | Date on which the metadata was checked. |
| used_for | Parameter, boundary, or screening use in the release. |
| evidence_boundary | What the evidence supports and the limit of that support. |
| redistribution_status | States that only metadata or an author aggregate is redistributed. |
| licence_or_rights_status | Source-specific rights for third-party material; CC BY 4.0 only for author-generated aggregate rows. |
| notes | Traceability note such as source-manifest evidence class or derivation. |

An open URL is not treated as an open licence. Third-party rows therefore
remain metadata-only unless source-specific redistribution rights are verified.
