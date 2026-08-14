# Controlled-input register dictionary

controlled_inputs_metadata.csv records restricted inputs that are required
for a full network-model rerun but are not distributed in this public
repository.

| Field | Meaning |
| --- | --- |
| dataset_id | One of the four approved restricted-input families. |
| data_class | High-level class of the absent payload. |
| share_status | Must be exactly metadata-only; no controlled payload is redistributed. |
| owner_or_provenance | Owner or authoritative provenance named for access review. |
| restriction_reason | Why the payload is excluded from this public release. |
| schema_summary | Human-readable description of the expected fields or objects. |
| access_route | Route for a future authorized request; say when access is subject to owner approval. |
| sha256 | 64 lowercase hexadecimal checksum when the payload is legitimately available. It is empty when no hash is available. |
| hash_note | When sha256 is empty this must begin with hash_unavailable: and contain a non-empty reason; when sha256 is a real digest this must be empty. All-zero placeholders are forbidden. |

The four current rows intentionally have empty sha256 values and explanatory
hash_note values. They do not imply that the restricted inputs can be
downloaded from this repository.
