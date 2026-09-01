# Green methanol pipeline reuse: full public reproducibility release

Package version `1.0.0` contains the public code, author-generated source
inputs, processed and model-ready carriers, figure source data, configuration,
tests, provenance records, and release inventories used for the green-methanol
pipeline-reuse study. The repository is the reproducibility package for the
registered manuscript outputs, including Figure 2e, which is reproduced from
the deposited public carrier.

## What this release reproduces

The full workflow regenerates every output registered in
`data/output_registry.csv`. It validates the deposited carriers, runs the
public demand/preprocessing, directed-flow, dynamic-analysis, and model
Figure 4/5 stages, then runs the six manuscript figure builders and checks all
expected artifacts. Run it from a clean checkout with an output directory
outside the repository:

```text
python scripts/reproduce.py --mode full --output <external-output>/green-methanol-full
```

The workflow includes the public Figure 2 carrier at
`data/figure_source/figure-02.csv`. Figure 2e can also be rebuilt directly:

```text
python scripts/build_figure_02.py --panel e --input data/figure_source/figure-02.csv --output figures/figure-02e.png
```

That command writes `figures/figure-02e.png` and `figures/figure-02e.pdf`.
Figure 2e is an analytical-coordinate network view, with the visible note
`Analytical coordinates; no official basemap`; its reproduction does not
depend on an external map download.

The four remaining figure commands are recorded verbatim in
`data/output_registry.csv` and rebuild Figures 1, 3, 4, and 5 from their
versioned source carriers. The model stages additionally regenerate public
demand nodes, directed NetworkX flow accounts, dynamic regional/logistics
tables, and model-derived Figure 4/5 source tables under
`data/processed/model_v01/`. Headline and model-ready carriers are retained
in `data/raw/`, `data/processed/`, and `data/author_derived/`.

## Install, test and audit

Create the environment outside the release payload, then install the pinned
requirements and package:

```text
python -m venv <external-venv>
<external-venv>/Scripts/python -m pip install -r environment/requirements.txt
<external-venv>/Scripts/python -m pip install -e .
<external-venv>/Scripts/python -m pytest -q
<external-venv>/Scripts/python scripts/reproduce.py --mode full --output <external-output>/green-methanol-full
<external-venv>/Scripts/python scripts/build_manifest.py
<external-venv>/Scripts/python scripts/audit_release.py --output <external-output>/green-methanol-audit.json
```

`FILE_MANIFEST.csv` and `CHECKSUMS.sha256` are deterministic inventories of
the release tree. The dataset and output registries are the authoritative
mapping from each input or manuscript output to its repository location and
generating command. A full run report contains all eleven output IDs, return
codes, artifact hashes, and sanitized logs. NetworkX flow uses the public
directed segment/node carriers and reports model-derived accounts; it does not
claim engineering qualification or observational status.

The optional pre-commit boundary guard checks Git index paths without opening
payload files. Install it with `pre-commit install`, or run
`python scripts/check_public_boundary.py` directly before committing.

## Public data and provenance

Author-generated raw, processed, model-ready, and figure-source material
outside the private-directory boundary is included in the repository. Use
`data/dataset_registry.csv` for dataset-to-path, provenance, access route,
source terms, hashes, and processing metadata. Use `data/public_sources.csv`
for source citations and evidence boundaries.

Third-party payloads are handled by their source terms. When a payload cannot
be redistributed, the repository keeps its metadata and official acquisition
route, together with any lawful derived carrier needed by the workflow. The
GS(2023)2767 entry is the metadata-only record at
`data/external/maps/standard_map_gs2023_2767.json`; Figure 2e uses its public
analytical-coordinate carrier and does not present a substitute official map.

The only exclusion is material located under a directory whose path component
is exactly `管道数据`. This user-private material is not included, read,
copied, inventoried, or disclosed. The full reproduction workflow does not depend on this directory.
The manuscript and Supplementary Information DOCX authority
files are represented by filenames and digests in `MANUSCRIPT_SCOPE.md`; the
DOCX binaries are not part of this repository.

## Licensing

Code and documentation are covered by the MIT notice in `LICENSE`. The
separate `LICENSE-DATA` file lists the exact author-generated aggregate
carriers covered by CC BY 4.0. Other data and metadata retain the source or
author terms recorded in the registries; repository presence does not relicense
third-party material or add rights beyond those terms. `NOTICE.md` records the
same boundary in concise form.

## Repository and version

Repository: <https://github.com/Chenzhongdaji/green-methanol-pipeline-reuse-public>

The checked package version is `1.0.0`, matching `pyproject.toml` and
`CITATION.cff`. Please cite the repository using `CITATION.cff`.
