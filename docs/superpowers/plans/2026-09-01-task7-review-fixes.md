# Task 7 review fixes implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Each behavior change must have a failing regression test before production code changes.

**Goal:** Close the remaining public-release review findings while preserving the public-only boundary and making Figure 2e PNG/PDF and path-safety checks fully reproducible.

**Architecture:** Treat `data/dataset_registry.csv` and `data/output_registry.csv` as the authoritative public contracts. Extend each output row with a deterministic secondary-artifact field, validate both artifacts before and after subprocess execution, expose both hashes in the full report, and derive manifest rows from the same registry metadata. Centralize post-resolution denylist and repository-containment checks at every read/hash boundary; use top-down walkers with fail-closed `onerror` callbacks.

**Tech Stack:** Python 3.12, pytest, CSV/JSON, SHA-256, GitHub Actions.

## Global Constraints

- Do not inspect, traverse, read, or hash any directory whose exact path component is `管道数据`.
- Do not modify release documents outside the explicitly expanded review-fix file scope.
- Do not push, tag, or create a release.
- Preserve deterministic LF/UTF-8 manifests and checksums.
- All production behavior changes require a test that was observed failing first.

---

### Task 1: Lock the review findings with failing tests

**Files:**
- Modify: `tests/test_release_closure.py`
- Modify: `tests/test_inventory.py`
- Modify: `tests/test_reproduce.py`
- Modify: `tests/test_audit.py`

- [ ] Add tests that assert no public release payload contains the legacy candidate/restricted/unavailable/withheld wording and that the audit rejects a regression in any of the five named panel/aggregate/output-registry files.
- [ ] Add tests that mutate a resolved symlink alias to the excluded component and assert it fails before file reads or hashes.
- [ ] Add tests that make `os.walk` report an `onerror` failure and assert inventory/audit fail closed.
- [ ] Add tests that require a `secondary_artifacts` field, register Figure 2e PDF, execute full reproduction, and assert the report includes PNG and PDF artifact paths and SHA-256 values.
- [ ] Run only the new tests and record the expected failures before touching production code.

### Task 2: Implement registry and full-report PDF closure

**Files:**
- Modify: `src/green_methanol_release/inventory.py`
- Modify: `src/green_methanol_release/pipeline.py`
- Modify: `src/green_methanol_release/reproduce.py`
- Modify: `data/output_registry.csv`
- Modify: `data/dictionaries/output_registry.md`

- [ ] Extend the output registry schema with deterministic secondary-artifact paths and validate safe relative paths, uniqueness, and the Figure 2e PDF contract.
- [ ] Make the orchestrator validate, hash, and report every primary and secondary artifact after each builder completes.
- [ ] Ensure Figure 2e requires `figure-02-source-real` and declares both `figures/figure-02e.png` and `figures/figure-02e.pdf`.
- [ ] Run the registry/orchestrator tests and confirm they pass.

### Task 3: Implement path and walker safety

**Files:**
- Modify: `src/green_methanol_release/inventory.py`
- Modify: `src/green_methanol_release/audit.py`
- Modify: `src/green_methanol_release/reproduce.py`
- Modify: `src/green_methanol_release/safety.py` only if the shared guard needs a narrow extension

- [ ] Add one post-resolution helper that checks the exact excluded component and containment below the release root before every open/hash/read operation.
- [ ] Apply it to registry carriers, manifest/checksum rows, reproduction inputs/outputs, and audit payload iteration.
- [ ] Configure walker `onerror` handlers to raise a release-specific failure rather than silently omit unreadable entries.
- [ ] Run path-safety and walker tests, then the full targeted suite.

### Task 4: Remove stale public-boundary wording

**Files:**
- Modify: `MANUSCRIPT_SCOPE.md`
- Modify: `figures/panel_map.csv`
- Modify: `data/dictionaries/panel_map.md`
- Modify: `data/author_derived/figure2_aggregate_source.csv`
- Modify: `data/dictionaries/figure2_aggregate_source.md`
- Modify: `src/green_methanol_release/audit.py` and related tests as needed

- [ ] Replace candidate/interim/restricted/unavailable/withheld language with the current public full-reproduction contract.
- [ ] State that Figure 2e consumes `figure-02-source-real` and emits registered PNG/PDF artifacts.
- [ ] Extend audit scanning and regression tests to cover these files.
- [ ] Run the wording tests and audit.

### Task 5: Regenerate and close the release

**Files:**
- Modify: `FILE_MANIFEST.csv`
- Modify: `CHECKSUMS.sha256`
- Modify: `.github/workflows/ci.yml` only if the expanded checks need CI wiring
- Modify: `tests/test_release_closure.py` only for final contract assertions

- [ ] Run the full targeted suite and `python -m pytest -q`.
- [ ] Run full reproduction twice and compare external output hashes.
- [ ] Regenerate manifest/checksum twice and compare bytes.
- [ ] Run pre-manifest and final audits plus `git diff --check`.
- [ ] Update `.superpowers/sdd/task-7-report.md` with evidence, then commit the review fixes without push/tag/release.
