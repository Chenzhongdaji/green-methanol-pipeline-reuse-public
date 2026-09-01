# Code Availability

Package version `1.0.0` provides the Python package under
`src/green_methanol_release/`, the command-line builders and audit tools under
`scripts/`, the pinned environment in `environment/`, configuration and
registries, tests, and the expected release inventories. The code reproduces
the public demand/preprocessing, directed NetworkX flow, dynamic-analysis,
model-v01 Figure 4/5 diagnostic sources, and six manuscript figure outputs,
including Figure 2e. Figure 2e is reproduced from its deposited public
carrier. `model-figure-04` and `model-figure-05` are model-derived
diagnostics, not formal manuscript figures or v08 numerical reproductions.

From a clean checkout, install Python 3.12 and the pinned requirements, then
run:

```text
python -m pip install -r environment/requirements.txt
python -m pip install -e .
python -m pytest -q
python scripts/reproduce.py --mode full --output <external-output>/green-methanol-full
python scripts/build_manifest.py
python scripts/audit_release.py --output <external-output>/green-methanol-audit.json
```

The full command consumes the dataset and output registries, validates every
registered carrier and its hash, executes the registered builders in registry
order, checks the expected artifacts, and writes sanitized logs plus
`full_reproduction.json` to the external output directory. The model rows run
from public raw carriers through demand allocation, directed flow, dynamic
accounts, and model-v01 Figure 4/5 source regeneration. The network model
uses `同管道运输任务_万吨` for occupied capacity and WGS84 haversine
kilometres for `distance_km` and `pipeline_tonne_km`; candidate links are
Figure-5 sensitivity inputs only. Legacy pressure/cost details are not
represented, and transport emissions are reserved/not implemented. Figure 2e is
explicitly bound to:

```text
python scripts/build_figure_02.py --panel e --input data/figure_source/figure-02.csv --output figures/figure-02e.png
```

The builder emits both the PNG and PDF outputs. Its network panel uses the
public analytical-coordinate carrier and is therefore reproducible without an
official basemap or network download. The other figure commands and their
input mappings are maintained in `data/output_registry.csv`.

Repository-local tests cover path safety, registry schemas, carrier hashes,
figure-source contracts, numerical checks, deterministic figures, the full
orchestrator, and release audits. Generated reports should be written outside
the repository so that frozen inputs are not overwritten.

Code and documentation are covered by the MIT notice in `LICENSE`. Data terms
are separate: `LICENSE-DATA` names its exact CC BY 4.0 aggregate allowlist,
while all other data and third-party materials retain the terms recorded in
the registries. The only private-directory exclusion is a path component
exactly equal to `管道数据`; the code does not require or inspect it.

Repository: <https://github.com/Chenzhongdaji/green-methanol-pipeline-reuse-public>

Checked package version: `1.0.0`.
