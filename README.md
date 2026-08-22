# Green methanol pipeline reuse: Level-1 release candidate

## What this release reproduces

This provisional `v1.0.0` candidate provides an offline Level 1 aggregate
reproduction of the reported headline accounts. Run the smoke workflow from
the repository root:

```text
python scripts/reproduce.py --mode smoke --output <external-output>/green-methanol-smoke.json
```

The released CSV carriers and dictionaries reproduce the pooled S1–S8, 2060
mid-demand aggregate checks. Figure source carriers cover Figures 1 and 3-5
and the safe aggregate subset of Figure 2 panels a-d and f-h. Figure 2 panel e
is withheld because it depends on restricted network/map payloads and pending
formal map review. The workflow is intentionally bounded to reviewed aggregate
data and metadata. No network download is required by the runtime.

## What this release does not reproduce

Level 2 full network-model rerun is `NOT_REPRODUCED`. Exact directed topology,
physical nodes and edges, facility-to-trunk/refinery mappings, candidate-link
geometry, and the GS(2023)2767 map carriers are controlled or rights-limited
inputs and are not included. Their metadata remain in the controlled-input
register; proximity or aggregate shares must not be read as proof of a usable
pipeline connection.

The manuscript and Supplementary Information DOCX files are not redistributed.
The candidate is bound to the current rev04 public-data/code pair and SHA-256 values recorded in
[MANUSCRIPT_SCOPE.md](MANUSCRIPT_SCOPE.md). This package contains neither
third-party raw source payloads nor a DOI claim. See
[DATA_AVAILABILITY.md](DATA_AVAILABILITY.md) and
[CODE_AVAILABILITY.md](CODE_AVAILABILITY.md) for separate availability scopes.

## Install, test and audit

From a clean checkout, create an environment outside the release payload and
install the pinned requirements and package:

```text
python -m venv <venv>
<venv>/Scripts/python -m pip install -r environment/requirements.txt
<venv>/Scripts/python -m pip install -e .
<venv>/Scripts/python -m pytest -q
<venv>/Scripts/python scripts/reproduce.py --mode smoke --output <external-output>/green-methanol-smoke.json
<venv>/Scripts/python scripts/audit_release.py --pre-manifest --output <external-output>/green-methanol-audit.json
```

The audit must report `status=PASS` after the deterministic manifest and
checksum files are present. A manifest-closed candidate is still not a public
archive or publication; external archive, author, rights and identifier gates
remain recorded in [RELEASE_STATUS.md](RELEASE_STATUS.md).

`FILE_MANIFEST.csv` covers every release payload except itself and
`CHECKSUMS.sha256`. `CHECKSUMS.sha256` covers those payloads plus
`FILE_MANIFEST.csv`, but excludes itself, so regeneration has no self-reference
cycle.

## Reproduction levels and layout

- **Level 1 — open aggregate reproduction:** inventory validation, panel-map
  checks, dictionary coverage, and recomputation of the headline aggregate
  percentages.
- **Level 2 — full network-model rerun:** `NOT_REPRODUCED` because the
  controlled topology, facility mapping, candidate geometry, and map inputs are
  absent.

`data/public_sources.csv` records source metadata without copying source files.
`data/controlled_inputs_metadata.csv` records restricted-input provenance and
non-sensitive validation substitutes only.
Author-generated aggregate carriers are explicitly labelled and are the only
data covered by the candidate's CC BY 4.0 terms; code and documentation are
covered by MIT as described in [NOTICE.md](NOTICE.md).

## Release metadata

Release candidate version: `v1.0.0` (initial candidate 2026-08-14;
metadata rebound to the current rev04 public-data/code manuscript on 2026-08-22).
The public development repository is
<https://github.com/Chenzhongdaji/green-methanol-pipeline-reuse-public>.
The repository is a provisional candidate rather than a frozen archival
release: no release tag, DOI or accession number has yet been assigned.
The private-development source commit `origin/main d0c13d0` is recorded only as
provenance and is not a public repository claim.
