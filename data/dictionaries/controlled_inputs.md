# Controlled-input register dictionary

`data/controlled_inputs_metadata.csv` records restricted inputs needed for a
full network-model rerun; controlled payloads are not distributed here.

| Column | Definition | Unit or codes | Missing-value policy | Derivation | Related panel |
| --- | --- | --- | --- | --- | --- |
| dataset_id | Stable identifier for an approved restricted-input family. | text | blank forbidden | metadata transcription from the controlled-input manifest | network_model |
| data_class | High-level class of the absent payload. | text | blank forbidden | controlled vocabulary assignment | network_model |
| share_status | Public-release sharing state for the payload. | metadata-only | blank forbidden | restriction review annotation | network_model |
| owner_or_provenance | Owner or authoritative provenance named for access review. | text | blank forbidden | metadata transcription | network_model |
| restriction_reason | Reason the payload is excluded from this public release. | text | blank forbidden | restriction review annotation | network_model |
| schema_summary | Human-readable description of expected fields or objects. | text | blank forbidden | schema metadata transcription | network_model |
| access_route | Route for a future authorized request. | text | blank forbidden | access-process annotation | network_model |
| sha256 | Checksum when a legitimately available payload was hashed. | 64 lowercase hexadecimal or not_applicable | explicit not_applicable allowed only when unavailable | checksum transcription or absence annotation | network_model |
| hash_note | Explanation for an unavailable checksum or checksum provenance note. | text | blank forbidden | checksum audit annotation | network_model |

The current rows intentionally describe restricted inputs without redistributing
their payloads. A missing checksum is not an all-zero placeholder.
