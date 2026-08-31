# Full Public Data and Reproducibility Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the bounded Level-1 candidate into a tested public package that reproduces the manuscript, including Figure 2e, while never reading or publishing any path component named `管道数据`.

**Architecture:** Add a denylist-first staging layer and a machine-readable dataset/output registry, then migrate the approved author-generated and lawfully redistributable inputs from the frozen research checkout. Replace the stub full-mode runner with an orchestrator that validates inputs, runs preprocessing/model/figure commands, and checks outputs before regenerating release metadata.

**Tech Stack:** Python 3.12, pathlib, csv/json/hashlib, pytest, existing project model and figure modules, Git/GitHub Actions.

## Global Constraints

- No file inside any directory named `管道数据` may be read, copied, inventoried, committed or disclosed.
- Author-generated raw, processed, model-ready and figure-source data required by the manuscript are public by default.
- Third-party files are deposited only when redistribution is confirmed; otherwise use an official acquisition route, exact version metadata, checksum and lawful derived carrier.
- Figure 2e and every claimed manuscript output must have public inputs, a generating command and an automated check.
- Do not claim a DOI, accession, release tag, licence or permission before it exists and is verified.
- Use test-driven changes and commit each independently testable task.

---

### Task 1: Enforce the excluded-directory boundary

**Files:**
- Create: `src/green_methanol_release/safety.py`
- Create: `tests/test_safety.py`
- Modify: `src/green_methanol_release/audit.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `assert_public_path(path: Path) -> None`, `audit_tracked_paths(paths: Iterable[str]) -> list[str]`.

- [ ] **Step 1:** Add failing tests proving any path component exactly equal to `管道数据` is rejected while ordinary pipeline-named files remain allowed.
- [ ] **Step 2:** Run `python -m pytest tests/test_safety.py -v`; expect failures because `safety.py` does not exist.
- [ ] **Step 3:** Implement component-wise `PurePath.parts` checks and add `/管道数据/` plus `管道数据/` to `.gitignore`.
- [ ] **Step 4:** Extend the release audit to inspect `git ls-files -z` output and fail on forbidden components without opening those paths.
- [ ] **Step 5:** Run `python -m pytest tests/test_safety.py tests/test_audit.py -v`; expect PASS.
- [ ] **Step 6:** Commit with `git commit -m "feat: enforce private pipeline-data boundary"`.

### Task 2: Build the dataset-to-output registry

**Files:**
- Create: `data/dataset_registry.csv`
- Create: `data/output_registry.csv`
- Create: `data/dictionaries/dataset_registry.md`
- Create: `data/dictionaries/output_registry.md`
- Modify: `src/green_methanol_release/inventory.py`
- Modify: `tests/test_inventory.py`

**Interfaces:**
- Produces: `load_dataset_registry(path: Path) -> list[dict[str, str]]`, `load_output_registry(path: Path) -> list[dict[str, str]]`, `validate_release_registry(root: Path) -> dict[str, int]`.

- [ ] **Step 1:** Write failing schema tests requiring dataset ID, public path, role, origin, access route, licence, SHA-256, acquisition command, processing command and manuscript uses; require output ID, manuscript location, command, inputs and expected artifact.
- [ ] **Step 2:** Run `python -m pytest tests/test_inventory.py -v`; expect registry-file failures.
- [ ] **Step 3:** Implement strict CSV loaders, unique-ID checks, relative-path normalization, forbidden-path rejection and referential integrity between outputs and datasets.
- [ ] **Step 4:** Seed rows for existing Figure 1 and Figures 2-5 carriers, then add one explicit `figure-02e` output row rather than a withheld/status placeholder.
- [ ] **Step 5:** Run `python -m pytest tests/test_inventory.py -v`; expect PASS.
- [ ] **Step 6:** Commit with `git commit -m "feat: add dataset and output registries"`.

### Task 3: Stage approved reproducibility inputs

**Files:**
- Create: `scripts/stage_public_inputs.py`
- Create: `tests/test_stage_public_inputs.py`
- Create/Populate: `data/raw/`
- Create/Populate: `data/external/`
- Create/Populate: `data/processed/`
- Create/Populate: `data/figure_source/`

**Interfaces:**
- Consumes: registry loader and `assert_public_path` from Tasks 1-2.
- Produces: `stage_inputs(registry: Path, source_root: Path, release_root: Path) -> dict[str, object]` and `qa/staging_report.json`.

- [ ] **Step 1:** Write tests using temporary safe and forbidden source trees; assert byte-for-byte copies, hash verification, refusal before opening forbidden sources, and failure for undeclared files.
- [ ] **Step 2:** Run `python -m pytest tests/test_stage_public_inputs.py -v`; expect import failure.
- [ ] **Step 3:** Implement registry-driven copying only; do not recursively scan the research root. Record source-relative identifier, destination and SHA-256 without recording forbidden-directory contents.
- [ ] **Step 4:** Populate the registry from the frozen `727修改/.worktrees/city-topology-v01` source chain and other author-generated inputs outside the exclusion, including directed topology, facility mapping, candidate links, scenario inputs and Figure 2e carriers needed by the approved manuscript.
- [ ] **Step 5:** Classify each third-party item as `redistributable` or `acquire`; for `acquire`, add an official URL/download command and retain only lawful derived carriers.
- [ ] **Step 6:** Run staging, then `python -m pytest tests/test_stage_public_inputs.py tests/test_inventory.py -v`; expect PASS and a zero-error staging report.
- [ ] **Step 7:** Commit with `git commit -m "data: add full public reproduction inputs"`.

### Task 4: Replace the full-mode reproduction stub

**Files:**
- Create: `src/green_methanol_release/pipeline.py`
- Modify: `src/green_methanol_release/reproduce.py`
- Modify: `scripts/reproduce.py`
- Modify: `tests/test_reproduce.py`

**Interfaces:**
- Consumes: dataset/output registries and staged data.
- Produces: `run_full(root: Path, output_root: Path) -> dict[str, object]` with status `PASS`, executed commands, artifacts, hashes and numerical checks.

- [ ] **Step 1:** Replace tests that require `NOT_REPRODUCED` with failing tests requiring ordered acquisition validation, preprocessing, model execution, figure building and output validation.
- [ ] **Step 2:** Run `python -m pytest tests/test_reproduce.py -v`; expect failures on the old stub contract.
- [ ] **Step 3:** Implement subprocess execution from the output registry with fixed working directory, captured logs, non-zero exit propagation and expected-artifact/hash checks.
- [ ] **Step 4:** Connect the migrated model and preprocessing entry points; remove hard-coded controlled-input families and unconditional `NOT_REPRODUCED` branches.
- [ ] **Step 5:** Run `python scripts/reproduce.py --mode full --output qa/full_reproduction`; expect JSON `status: PASS`.
- [ ] **Step 6:** Run `python -m pytest tests/test_reproduce.py -v`; expect PASS.
- [ ] **Step 7:** Commit with `git commit -m "feat: enable full manuscript reproduction"`.

### Task 5: Make Figure 2e reproducible

**Files:**
- Create: `scripts/build_figure_02.py`
- Create: `tests/test_figure_02.py`
- Create: `figures/source_data/figure-02.csv`
- Create: `figures/figure-02.png`
- Create: `figures/figure-02.pdf`
- Modify: `figures/panel_map.csv`
- Modify: `data/output_registry.csv`

**Interfaces:**
- Produces: `build_figure_02(root: Path, output_dir: Path) -> dict[str, Path]`; panel `e` consumes public directed-edge geometry/flow/status fields and a legally distributable or officially acquirable map boundary.

- [ ] **Step 1:** Write failing tests requiring panel letters a-h, a non-empty panel-e record set, declared coordinate reference system, deterministic source-data columns and both raster/vector outputs.
- [ ] **Step 2:** Run `python -m pytest tests/test_figure_02.py -v`; expect missing-builder failures.
- [ ] **Step 3:** Port the approved Figure 2 builder from the frozen research checkout, replacing absolute paths with registry lookups and writing the combined source-data carrier.
- [ ] **Step 4:** Build Figure 2 and visually inspect the panel-e topology/flow encoding against the approved manuscript figure; record the review in `qa/figure-02-visual-review.md`.
- [ ] **Step 5:** Run `python -m pytest tests/test_figure_02.py tests/test_figure2_aggregate_source.py -v`; expect PASS.
- [ ] **Step 6:** Commit with `git commit -m "feat: reproduce complete Figure 2"`.

### Task 6: Rewrite availability, release and licence metadata

**Files:**
- Modify: `README.md`
- Modify: `DATA_AVAILABILITY.md`
- Modify: `CODE_AVAILABILITY.md`
- Modify: `RELEASE_STATUS.md`
- Modify: `LICENSE-DATA`
- Modify: `NOTICE.md`
- Modify: `CITATION.cff`
- Delete: `data/controlled_inputs_metadata.csv`
- Delete: `data/dictionaries/controlled_inputs.md`
- Modify: `tests/test_audit.py`

**Interfaces:**
- Consumes: achieved full-reproduction report and dataset registry.
- Produces: exact dataset-to-location availability text and licence coverage consistent with the tested package.

- [ ] **Step 1:** Write failing audits that reject `provisional candidate`, `Level 1`, `NOT_REPRODUCED`, blanket `controlled or rights-limited`, and Figure 2e withholding language.
- [ ] **Step 2:** Run `python -m pytest tests/test_audit.py -v`; expect failures on current documentation.
- [ ] **Step 3:** Rewrite the documents to state achieved capabilities only, preserve third-party licence boundaries, and identify the sole private-directory exclusion without describing its contents.
- [ ] **Step 4:** Remove the obsolete controlled register and its code/test assumptions; bind citation metadata to the actual repository URL and verified version, leaving DOI absent until minted.
- [ ] **Step 5:** Run `python -m pytest tests/test_audit.py tests/test_contracts.py -v`; expect PASS.
- [ ] **Step 6:** Commit with `git commit -m "docs: publish full data and code availability"`.

### Task 7: Close manifests, checksums and continuous integration

**Files:**
- Modify: `scripts/build_manifest.py`
- Modify: `FILE_MANIFEST.csv`
- Modify: `CHECKSUMS.sha256`
- Modify: `.github/workflows/ci.yml`
- Modify: `src/green_methanol_release/audit.py`

**Interfaces:**
- Produces: deterministic manifest/checksum closure and CI full-reproduction evidence.

- [ ] **Step 1:** Add failing tests that require every tracked release artifact except explicitly documented Git metadata to appear once in the manifest and checksum list.
- [ ] **Step 2:** Run the targeted manifest tests; expect failure because migrated files are absent.
- [ ] **Step 3:** Update manifest generation to call the safety guard before hashing and to derive role/licence/provenance from registries.
- [ ] **Step 4:** Update CI to install the locked environment, run all tests, execute full reproduction and audit manifest closure.
- [ ] **Step 5:** Run `python scripts/build_manifest.py`, `python scripts/audit_release.py --json qa/release_audit.json`, and `python -m pytest -q`; expect zero audit errors and all tests passing.
- [ ] **Step 6:** Commit with `git commit -m "build: close reproducible public release"`.

### Task 8: Clean-clone verification and GitHub release

**Files:**
- Create: `qa/clean_clone_verification.json`
- Modify: `RELEASE_STATUS.md` only if verification changes achieved status.

**Interfaces:**
- Consumes: final repository commit.
- Produces: clean-clone evidence, pushed commit and verified frozen tag/release.

- [ ] **Step 1:** Clone the local repository into a new temporary directory outside the research workspace and verify no untracked source dependency is available.
- [ ] **Step 2:** Run environment installation, `python -m pytest -q`, full reproduction, audit and forbidden-path scan in the clone; require PASS for every command.
- [ ] **Step 3:** Record commit SHA, Python/dependency versions, test counts, reproduction status, artifact hashes and the zero-hit forbidden-path result in `qa/clean_clone_verification.json`.
- [ ] **Step 4:** Regenerate manifest/checksums, rerun final audit and commit the verification record with `git commit -m "release: verify clean public reproduction"`.
- [ ] **Step 5:** Push `main` to `origin`, verify the remote commit, then create and push the next semantic version tag only after remote CI passes.
- [ ] **Step 6:** Create the GitHub release from the verified tag. Do not add a DOI until an external archive has minted and resolved it.
