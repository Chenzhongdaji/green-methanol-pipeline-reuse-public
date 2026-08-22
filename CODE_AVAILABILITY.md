# Code Availability

Provisional candidate `v1.0.0` (initial candidate 2026-08-14; metadata rebound
2026-08-22) contains the following code and verification contract. Figure
source carriers cover Figures 1 and 3-5 and the safe aggregate subset of Figure
2 panels a-d and f-h; Figure 2 panel e remains withheld because it depends on
restricted network/map payloads.
The candidate is bound to the current rev03 data/code manuscript and Supplementary
Information pair recorded in [MANUSCRIPT_SCOPE.md](MANUSCRIPT_SCOPE.md).

The Python package under `src/green_methanol_release/` and the command-line
scripts under `scripts/` are provided under the MIT License for this candidate.
The declared
runtime is Python 3.12 with the pinned dependencies in
`environment/requirements.txt`; no repository-local virtual environment is
needed. The test suite is run with `pytest` and the smoke reproduction writes
its JSON report to a caller-selected external path.

The code implements the bounded Level 1 aggregate workflow, deterministic file
manifest/checksum generation, and the fail-closed release audit. It does not
contain an implementation route to the absent Level 2 topology, facility
mappings, candidate geometry, or map payloads. The public development
repository is
<https://github.com/Chenzhongdaji/green-methanol-pipeline-reuse-public>.
It has no frozen release tag, DOI or accession number; archival publication
remains blocked pending author confirmation and rights review.
