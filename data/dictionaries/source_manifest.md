# City-topology source manifest dictionary

`data/raw/city_topology_v01/source_manifest.csv` is a provenance index, not a
copy of every historical input. `local_path` is interpreted together with
`link_status` and `repository_source_id`:

| Field | Meaning |
| --- | --- |
| `source_id` | Stable identifier for the cited source or project record. |
| `local_path` | `external://...` for an external source, a release-relative repository path for a directly deposited public carrier, or `historical://...` for an unavailable historical artifact. `historical://` is metadata and is never opened or hashed. |
| `sha256` | Current SHA-256 for a `direct_public_carrier`; `not_applicable` for `external_only` and `historical_metadata_only`. |
| `link_status` | One of `external_only`, `direct_public_carrier`, or `historical_metadata_only`. |
| `repository_source_id` | Matching `data/dataset_registry.csv` ID for a direct carrier; `not_applicable` otherwise. |

The validator requires every direct carrier path and hash to match the current
repository registry and file bytes. Historical metadata rows preserve the
existence of an earlier model/source reference but do not establish that the
artifact can be reconstructed from this release. In particular, unavailable
v0.8 demand contracts, refinery-city allocation, and the legacy stage19--21
script remain historical metadata only.

`data/processed/dynamic_analyses_v08/c3_unlocking_cost.csv` uses the same
boundary for its `flow_source` field. Its 27 rows retain their historical
derived-flow reference as `historical://...` with
`flow_source_status=historical_metadata_only`; these rows are not a claim that
the old flow carrier is present or reproducible.
