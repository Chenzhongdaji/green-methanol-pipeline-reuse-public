# Code Availability

Release `v1.0.0` (2026-08-14) contains the following code and verification
contract.

The Python package under `src/green_methanol_release/` and the command-line
scripts under `scripts/` are released under the MIT License. The declared
runtime is Python 3.12 with the pinned dependencies in
`environment/requirements.txt`; no repository-local virtual environment is
needed. The test suite is run with `pytest` and the smoke reproduction writes
its JSON report to a caller-selected external path.

The code implements the bounded Level 1 aggregate workflow and the fail-closed
release audit. It does not contain an implementation route to the absent Level
2 topology, facility mappings, candidate geometry, or map payloads. The
repository is available at
`https://github.com/Chenzhongdaji/green-methanol-pipeline-reuse`.
