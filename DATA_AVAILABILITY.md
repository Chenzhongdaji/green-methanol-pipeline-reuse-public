# Data Availability

Package version `1.0.0` contains the author-generated raw, cleaned, processed,
model-ready, and figure-source carriers used by the registered reproduction
workflow, subject to one path-based private-directory boundary. The deposited
carriers include the directed network and node-coordinate tables, city and
activity inputs, demand and supply inputs, topology and flow tables, dynamic
analysis tables, and source data for Figures 1-5. Figure 2e is reproduced from
the public carrier at `data/figure_source/figure-02.csv`.

`data/dataset_registry.csv` is the authoritative dataset-to-location register;
it records 56 dataset records, including 55 deposited byte carriers and one
metadata-only acquisition record. Each record states its origin, access route,
source terms, SHA-256 value, processing information, and manuscript use.
`data/output_registry.csv` maps each of the five public model stages and six
manuscript figure outputs to its input dataset IDs and generating command.
`FILE_MANIFEST.csv` and
`CHECKSUMS.sha256` provide the final-tree inventory and byte checks.
The release-facing `reproduce.py` and `audit_release.py` commands take a
report-file path such as `full_reproduction.json` with `--output`; that option
does not denote an output directory.

The deposited model-v01 carriers include the demand, directed-network,
analysis, and Figure 4/5 diagnostic stages. The model-figure-04 and
model-figure-05 artifacts are diagnostic/model-derived outputs, not formal
manuscript figures and not numerical reproductions of v08. The directed
network uses `同管道运输任务_万吨` as its occupied-capacity basis and WGS84
haversine kilometres for `distance_km` and `pipeline_tonne_km`, retaining the
v08 one-km lower bound for coincident analytical coordinates; candidate
links are confined to Figure-5 sensitivity. Legacy pressure/cost details are
not represented, and transport-emission accounting is reserved/not
implemented.

The public source register at `data/public_sources.csv` records stable source
locators, versions, access dates, evidence boundaries, and source-specific
redistribution terms. A third-party payload that cannot be redistributed is
represented by metadata and an official acquisition route, with a lawful
derived carrier where the workflow uses one. The GS(2023)2767 record is the
metadata-only file at
`data/external/maps/standard_map_gs2023_2767.json`; no official map payload is
needed by the Figure 2e builder. Its carrier uses analytical coordinates and
does not claim to be an official basemap.

The only exclusion is material under a directory whose path component is
exactly `管道数据`. It is user-private material, is not included or disclosed,
and the full reproduction workflow does not depend on this directory. No other
directory is treated as a private data boundary by this release. The manuscript and
Supplementary Information DOCX authority files remain represented by metadata
and SHA-256 values in `MANUSCRIPT_SCOPE.md`; the binaries are not deposited.

The aggregate carriers explicitly listed in `LICENSE-DATA` are available under
CC BY 4.0. Other deposited data and metadata retain the source or author terms
identified in `data/dataset_registry.csv` and `data/public_sources.csv`; this
statement does not add a licence or permission to material outside that scope.

Repository: <https://github.com/Chenzhongdaji/green-methanol-pipeline-reuse-public>

Checked package version: `1.0.0`.
