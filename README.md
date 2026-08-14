# Green methanol pipeline reuse: public data and code release

## What this release reproduces

This release provides an offline Level 1 aggregate reproduction of the
reported headline accounts. Run the smoke workflow from the repository root:

```text
python scripts/reproduce.py --mode smoke --output <external-output>/green-methanol-smoke.json
```

The released CSV carriers and dictionaries reproduce the pooled S1–S8, 2060
mid-demand aggregate checks. The workflow is intentionally bounded to reviewed
aggregate data and metadata. No network download is required by the runtime.

## What this release does not reproduce

Level 2 full network-model rerun is `NOT_REPRODUCED`. Exact directed topology,
physical nodes and edges, facility-to-trunk/refinery mappings, candidate-link
geometry, and the GS(2023)2767 map carriers are controlled or rights-limited
inputs and are not included. Their metadata remain in the controlled-input
register; proximity or aggregate shares must not be read as proof of a usable
pipeline connection.

The manuscript DOCX is not redistributed. This repository contains neither
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

The pre-manifest audit is expected to report `status=PASS` with
`public_release=BLOCKED_MANIFEST`; the later manifest-generation step closes
the release for publication.

## Reproduction levels and layout

- **Level 1 — open aggregate reproduction:** inventory validation, panel-map
  checks, dictionary coverage, and recomputation of the headline aggregate
  percentages.
- **Level 2 — full network-model rerun:** `NOT_REPRODUCED` because the
  controlled topology, facility mapping, candidate geometry, and map inputs are
  absent.

`data/public_sources.csv` records source metadata without copying source files.
`data/controlled_inputs_metadata.csv` records restricted-input provenance only.
Author-generated aggregate carriers are explicitly labelled and are the only
data covered by the repository's CC BY 4.0 grant; code and documentation are
covered by MIT as described in [NOTICE.md](NOTICE.md).

## Release metadata

Release version: `v1.0.0` (2026-08-14). The target repository is
`https://github.com/Chenzhongdaji/green-methanol-pipeline-reuse`.
