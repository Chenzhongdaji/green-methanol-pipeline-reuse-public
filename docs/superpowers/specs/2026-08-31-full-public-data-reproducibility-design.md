# Full public data and reproducibility release design

Date: 2026-08-31

## Objective

Replace the current bounded Level-1 candidate with a submission-ready public
repository that contains every input, intermediate, source-data carrier,
configuration and script needed to reproduce the manuscript results and
figures, including Figure 2e, subject to one explicit exclusion: no file located
inside any directory named `管道数据` may be read, copied, inventoried, committed
or disclosed.

## Release boundary

The repository will include all relevant author-generated material outside the
excluded directory: raw inputs, cleaned and derived inputs, model-ready tables,
scenario configurations, source data for every figure and table, processing and
model code, environment specifications, tests, provenance records, manifests
and checksums.

Third-party material will follow a lawful redistribution decision for each
dataset. Files with confirmed redistribution permission will be deposited.
Where permission cannot be confirmed, the repository will contain an official
source URL or deterministic acquisition script, precise version and access
metadata, a checksum for the exact source used when lawfully recordable, and
the minimum lawful derived carrier needed for reproduction. A generic
`rights-limited` label is not an acceptable substitute for this record.

The excluded `管道数据` directory is a hard path-based denylist. The release
workflow must not inspect its filenames or contents. A pre-commit/release guard
will fail if a tracked path contains that directory component or if release
documentation accidentally lists its contents.

## Repository architecture

The public package will separate:

- `data/raw/`: redistributable source inputs frozen at the versions used;
- `data/external/`: third-party acquisition records and lawful cached files;
- `data/processed/`: deterministic preprocessing outputs used by the model;
- `data/figure_source/`: explicit carriers for every manuscript and
  supplementary figure panel;
- `scripts/` and `src/`: acquisition, preprocessing, modelling, figure and
  audit code;
- `configs/` and `environment/`: scenario and executable-environment locks;
- `tests/` and `qa/`: contracts, numerical checks and reproduction evidence;
- root release metadata: README, availability statements, licences, citation
  metadata, file manifest, checksums and release status.

Existing paths may be retained where migration would add risk, but the manifest
must map every manuscript output to its exact inputs and generating command.

## Reproduction flow

A clean-checkout workflow will perform, in order: acquire or validate external
inputs; validate raw and processed schemas; regenerate required intermediates;
run the manuscript model; regenerate figure source carriers and figures; compare
headline values and deterministic artifacts against approved references; and
regenerate the manifest and checksums.

The former `Level 1`/`Level 2` split and unconditional `NOT_REPRODUCED` contract
will be removed. Figure 2e will have a concrete public input contract, build
command and output test. If an input outside `管道数据` cannot be deposited, its
official acquisition route and lawful derived carrier must still make the clean
workflow executable; otherwise the release fails rather than claiming full
reproducibility.

## Documentation and licensing

README, Data Availability, Code Availability, release status, notices and data
dictionaries will describe the achieved public package rather than a
provisional candidate. They will not claim a DOI, accession, archive, release
tag, licence or permission until it exists and has been checked.

Code licensing and data licensing remain distinct. Author-generated data will
receive an explicit open-data licence selected for the release. Third-party
files retain their source terms and will not be relicensed by implication.
Dataset-to-location mappings, provenance and citation metadata will be explicit.

## Error handling and safeguards

- Missing, changed or inaccessible inputs fail with the dataset identifier and
  remediation route.
- Hash or schema mismatches fail before modelling.
- The path denylist fails before staging, manifest generation and release.
- Generated artifacts are written to controlled output paths and cannot silently
  overwrite frozen raw inputs.
- Unresolved redistribution rights select the acquisition-and-derived-carrier
  route; they do not silently omit a required dataset.

## Verification and acceptance

The release is accepted only when:

1. a clean checkout can execute the documented full workflow;
2. Figure 2e and all other claimed figures/tables are regenerated from public
   repository inputs or documented lawful acquisition routes;
3. headline numerical checks and figure-source contracts pass;
4. no tracked path or disclosed inventory entry originates in `管道数据`;
5. every supporting dataset has provenance, access route, licence boundary and
   manuscript-output mapping;
6. the file manifest and SHA-256 list match the final tree;
7. README and availability statements match tested repository capabilities;
8. the final commit is pushed to the configured GitHub remote; and
9. a frozen version tag/release is created only after the final tree passes all
   checks. A DOI remains an external archive action and is never fabricated.

## Scope exclusions

This work does not publish anything from `管道数据`, invent permissions or
persistent identifiers, or upload unrelated drafts and temporary workspace
artifacts. Manuscript prose changes are limited to availability and
reproducibility claims unless a separate revision is approved.
