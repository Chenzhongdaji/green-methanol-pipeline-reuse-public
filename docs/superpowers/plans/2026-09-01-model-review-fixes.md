# Public model review fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct model-v01 capacity, distance, stage isolation, candidate-sensitivity, and diagnostic-output semantics while preserving a deterministic public release.

**Architecture:** Keep the existing release-relative public model package, but make each registered CLI stage load only its declared public inputs and write only its declared artifacts. Use the original v08 task-level capacity field (`同管道运输任务_万吨`) as the segment capacity, calculate all distances in kilometres with one haversine helper, and keep candidate links in a Figure-5-only counterfactual branch.

**Tech Stack:** Python 3.12, pandas 3.0.1, NumPy 2.5.1, NetworkX 3.5, Matplotlib 3.11.1, pytest 8.4.2, CSV/JSON registries, SHA-256 manifests.

## Global Constraints

- Never read, list, hash, copy, or otherwise access any directory whose path component is the protected name from the task contract.
- Do not use repository-parent paths, package caches, or machine-absolute inputs; every model input must be release-relative and registry-declared.
- Preserve `distance_km` and `pipeline_tonne_km` names; document omitted legacy pressure/cost details.
- Candidate links are sensitivity-only for Figure 5 and must not enter the base graph.
- Fail closed on candidate links that reference unknown public nodes.
- Keep model-v01 outputs explicitly diagnostic/model-derived, not formal manuscript figures or v08 numerical replicas.
- Use red-green TDD for every behavior change, then run targeted/full verification before claiming completion or committing.

---

### Task 1: Lock review findings into failing tests

**Files:**
- Modify: `tests/test_model_chain.py`
- Modify: `tests/test_release_closure.py`
- Modify: `tests/test_reproduce.py`
- Create: `tests/test_model_stage_isolation.py`

**Interfaces:**
- Tests will exercise `run_network`, `run_model_stage`, `run_model_chain`, and the registered output commands without introducing test-only production APIs.
- Expected network summary/edge schema will include `capacity_basis` and `candidate_scope`; distance fields remain `distance_km` and `pipeline_tonne_km`.

- [x] **Step 1: Write failing capacity/distance tests.**

  Add a fixture using a known transport-task row whose `同管道运输任务_万吨` differs from a whole-network connected total; assert the model uses the task value for that segment and that haversine distance is within a small tolerance of the two endpoint coordinates. Assert candidate sensitivity rows are separate from the base graph.

- [x] **Step 2: Write failing candidate validation tests.**

  Feed a candidate link with a node absent from the public base-node carrier and assert `run_dynamic_analysis` raises `ValueError` mentioning the unknown node.

- [x] **Step 3: Write failing stage-isolation tests.**

  Invoke each model CLI in an empty temporary output root with its exact registry inputs and assert only its declared artifact set exists: demand writes only demand artifacts, network writes only network artifacts, analysis writes only analysis artifacts, and each figure writes only its figure artifact. Assert a network invocation does not read demand inputs outside the declared demand+network set by changing an undeclared downstream carrier and checking unchanged results.

- [x] **Step 4: Run the new tests and verify expected red.**

  Run:

  ```text
  .venv\\Scripts\\python.exe -m pytest -q tests/test_model_chain.py tests/test_model_stage_isolation.py tests/test_release_closure.py tests/test_reproduce.py
  ```

  Expected: failures for task-capacity semantics, distance scale, invalid candidate nodes, and downstream stage side effects.

### Task 2: Correct capacity and haversine distance semantics

**Files:**
- Modify: `src/green_methanol_release/model/network.py`
- Modify: `src/green_methanol_release/model/analysis.py`
- Modify: `config/model_parameters_v01.csv`
- Modify: `data/dictionaries/model_parameters.md`
- Modify: `data/processed/model_v01/network_model_audit.json`
- Modify: `data/processed/model_v01/dynamic_analysis_audit.json`
- Test: `tests/test_model_chain.py`

**Interfaces:**
- Add one internal `haversine_km(lon1, lat1, lon2, lat2) -> float` helper.
- Network edge records continue exposing `distance_km` and `pipeline_tonne_km`; add an explicit capacity-basis field and audit metadata.

- [x] **Step 1: Implement the smallest capacity fix.**

  Parse `同管道运输任务_万吨` from the transport-task carrier per segment/task, aggregate only duplicate rows for the same segment/task as appropriate, and use that value as the segment upper bound. Do not derive capacity from all edges reachable through the graph. Record `capacity_basis = "同管道运输任务_万吨"` and a non-empty audit explanation.

- [x] **Step 2: Implement haversine distance.**

  Read endpoint longitude/latitude from the public node carrier, compute the great-circle distance in kilometres for every base segment and candidate link, and use the same km scale in `pipeline_tonne_km` and transport cost. Reject missing/non-finite coordinates instead of silently substituting a different scale.

- [x] **Step 3: Mark transport emission as reserved.**

  Remove `transport_emission_per_km` from active calculations or mark it `reserved_not_implemented` in configuration, dictionary, and audits; ensure no output claims emissions are computed.

- [x] **Step 4: Run the focused tests and verify green.**

  Run:

  ```text
  .venv\\Scripts\\python.exe -m pytest -q tests/test_model_chain.py -k "capacity or distance or candidate"
  ```

  Expected: all corrected semantic tests pass.

### Task 3: Enforce strict stage input/output closure

**Files:**
- Modify: `src/green_methanol_release/model/workflow.py`
- Modify: `scripts/model/preprocess_demand.py`
- Modify: `scripts/model/run_network.py`
- Modify: `scripts/model/build_analysis.py`
- Modify: `scripts/model/build_figure_04.py`
- Modify: `scripts/model/build_figure_05.py`
- Modify: `data/output_registry.csv`
- Modify: `tests/test_model_stage_isolation.py`

**Interfaces:**
- `run_model_stage(root, stage, output_root=None)` must execute only the selected stage and return only that stage's outputs.
- Stage contracts: demand consumes `DEMAND_INPUTS` and writes demand artifacts; network consumes demand outputs plus `NETWORK_INPUTS` and writes network artifacts; analysis consumes demand/network outputs plus candidate sensitivity carriers and writes analysis artifacts; figures consume analysis source and write exactly one figure.

- [x] **Step 1: Separate stage functions before wiring.**

  Replace downstream recomputation in `run_model_stage` with explicit loaders for registered upstream carriers. Keep `run_model_chain` as the only function allowed to compose all stages in order.

- [x] **Step 2: Constrain each CLI.**

  Validate `--input` against that stage's exact registry input IDs, resolve all paths under the release root, and pass `output_root` to the stage writer. A figure CLI must not write source tables; it reads the registered analysis source.

- [x] **Step 3: Update registry and artifact contracts.**

  Replace broad repeated input lists with exact stage-specific inputs and exact primary/secondary artifact sets. Add hashes/schema references for every new carrier and make the stage isolation tests assert the registry contract.

- [x] **Step 4: Run stage-isolation tests and verify green.**

  Run:

  ```text
  .venv\\Scripts\\python.exe -m pytest -q tests/test_model_stage_isolation.py tests/test_reproduce.py
  ```

  Expected: each stage writes only its registered outputs and all full workflows remain reproducible.

### Task 4: Remove candidate links from base topology and document diagnostics

**Files:**
- Modify: `src/green_methanol_release/model/network.py`
- Modify: `src/green_methanol_release/model/analysis.py`
- Modify: `data/dictionaries/output_registry.md`
- Modify: `README.md`
- Modify: `CODE_AVAILABILITY.md`
- Modify: `RELEASE_STATUS.md`
- Modify: `.superpowers/sdd/task-model-report.md`
- Test: `tests/test_model_chain.py`

**Interfaces:**
- `run_network` returns a base graph built only from base public nodes/segments; candidate links are passed only to an explicitly named Figure-5 sensitivity calculation.
- Figure-5 source rows identify `base`, `capacity_relaxation`, and `candidate_sensitivity` branches and include provenance hashes for the base network and candidate carrier separately.

- [x] **Step 1: Add a base-graph closure assertion.**

  Build the base graph before loading candidates; assert no candidate edge ID is present in the base edge-flow output. Store separate `base_network_input_hashes` and `candidate_sensitivity_input_hashes`.

- [x] **Step 2: Fail fast on unknown candidate nodes.**

  Validate both endpoints against the base node set before calculating Figure-5 sensitivity; raise a clear `ValueError` for any missing endpoint.

- [x] **Step 3: Label diagnostic figures.**

  Update all release text and report language to call `model-figure-04/05` model-v01 diagnostic/model-derived outputs, not formal manuscript figures and not v08 numerical reproductions. State that pressure/cost details omitted from this public analytical model are not represented.

- [x] **Step 4: Run focused network/analysis tests.**

  ```text
  .venv\\Scripts\\python.exe -m pytest -q tests/test_model_chain.py tests/test_model_stage_isolation.py
  ```

### Task 5: Regenerate carriers, registry hashes, and complete release verification

**Files:**
- Modify: `data/processed/model_v01/*`
- Modify: `figures/model-figure-04.png`
- Modify: `figures/model-figure-05.png`
- Modify: `data/dataset_registry.csv`
- Modify: `data/output_registry.csv`
- Modify: `FILE_MANIFEST.csv`
- Modify: `CHECKSUMS.sha256`
- Modify: `qa/staging_report.json`
- Modify: `.superpowers/sdd/task-model-report.md`

- [x] **Step 1: Regenerate model outputs from the public chain.**

  Run all five registered model CLIs or the full workflow and verify deterministic row counts, finite values, non-empty capacities/distances, and changed output hashes relative to the pre-fix report.

- [x] **Step 2: Run required verification commands.**

  Run targeted tests, full `pytest -q`, two independent full reproductions with byte-identical reports, clean-clone carrier/hash tests, pre-manifest audit, manifest regeneration twice with byte-identical outputs, final audit, and `git diff --check`.

- [x] **Step 3: Commit the fix.**

  ```text
  git add <review-fix-files>
  git commit -m "fix: align public model chain with v08 review semantics"
  ```

- [x] **Step 4: Update the report with exact command evidence and scientific limits.**

  Record the capacity field, haversine km, stage closure, candidate-only provenance, diagnostic figure wording, all command outputs, and the remaining proxy/engineering boundaries. Do not push, tag, or release.
