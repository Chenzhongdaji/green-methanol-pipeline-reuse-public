# Release status

## Current package

This repository contains the checked public reproducibility package at version
`1.0.0`. The package includes the registered input carriers, executable code,
figure-source data, tests, provenance records, and release inventories. The
full workflow has been exercised against the five public model stages and
six manuscript figure output jobs and records PASS for all eleven outputs,
including Figure 2e. The two model-figure jobs are model-v01
diagnostic/model-derived outputs; they are not formal manuscript figures and
are not numerical reproductions of v08. Figure 2e is reproduced from the
deposited public carrier.

The repository URL is
<https://github.com/Chenzhongdaji/green-methanol-pipeline-reuse-public>.
The version is the value declared in `pyproject.toml` and `CITATION.cff`.

## Reproduction evidence

The input boundary is defined by `data/dataset_registry.csv`; manuscript-output
mapping and commands are defined by `data/output_registry.csv`. Run
`python scripts/reproduce.py --mode full --output <external-output>/green-methanol-full/full_reproduction.json`
to validate hashes, execute the builders, and write the machine-readable report
file plus sanitized logs. The `--output` value is a report file, not a
directory. Figure 2e is generated from
`data/figure_source/figure-02.csv` by
`scripts/build_figure_02.py --panel e` and produces both the PNG and PDF
artifacts. Its network view uses analytical coordinates and does not require
an official basemap.

The final-tree inventory is regenerated with `python scripts/build_manifest.py`
and checked with
`python scripts/audit_release.py --output <external-output>/green-methanol-audit.json`.
The public repository's CI repeats the test and audit contract. The directed
network uses `同管道运输任务_万吨` as the occupied-capacity basis and WGS84
haversine kilometres for `distance_km` and `pipeline_tonne_km`, retaining the
v08 one-km lower bound for coincident analytical coordinates. Candidate
links are confined to Figure-5 sensitivity. Legacy pressure/cost details are
omitted from this public analytical model; transport emissions are reserved
and not implemented.

## Data and rights boundary

Author-generated raw and derived carriers outside the private-directory
boundary are present in the paths named by the dataset registry. Third-party
source material remains under source-specific terms. For a payload that cannot
be redistributed, the repository records metadata and an official acquisition
route and retains a lawful derived carrier where needed. The GS(2023)2767 entry
at `data/external/maps/standard_map_gs2023_2767.json` is a metadata-only
acquisition record.

The only exclusion is material under a directory whose path component is
exactly `管道数据`. It is user-private material, is not included or disclosed,
and is not required by the full workflow. The manuscript authority filenames
and digests are recorded in `MANUSCRIPT_SCOPE.md`; the DOCX binaries are not
part of this repository.

Code and documentation use the MIT notice in `LICENSE`. The exact aggregate
data allowlist under CC BY 4.0 is in `LICENSE-DATA`; all other data and
metadata retain the terms stated in their registries.

## Citation

Use `CITATION.cff` to cite this repository and its checked package version.
