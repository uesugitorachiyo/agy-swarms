# Release Artifact Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish deterministic SHA-256 provenance for GitHub Release artifacts and document operator verification.

**Architecture:** Add a small script that generates a stable `SHA256SUMS.txt` manifest from built files in `dist/`. Wire the release workflow to create that manifest after `uv build` and attach it alongside the wheel and source distribution. Keep verification local and deterministic with unit tests over the manifest writer and workflow/docs contract tests.

**Tech Stack:** Python 3.11 standard library (`argparse`, `hashlib`, `pathlib`), GitHub Actions, pytest, mypy.

---

### Task 1: Pin Manifest Generation Behavior

**Files:**
- Create: `tests/test_release_artifact_manifest.py`

- [x] **Step 1: Write the failing manifest test**

Add tests that import `build_manifest`, `write_manifest`, and `main` from `scripts.release_artifact_manifest`. The tests should create fake wheel and sdist files, assert lexicographically stable SHA-256 manifest lines, and assert the CLI writes `SHA256SUMS.txt`.

- [x] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run python -m pytest tests/test_release_artifact_manifest.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'scripts.release_artifact_manifest'`.

### Task 2: Implement Manifest Generation

**Files:**
- Create: `scripts/release_artifact_manifest.py`
- Modify: `Makefile`
- Modify: `tests/test_quality_command_contracts.py`

- [x] **Step 1: Implement manifest functions and CLI**

Create a script that writes lines in the form `<sha256>  <filename>` for each supplied artifact path, sorted by filename. The default output path is `dist/SHA256SUMS.txt`.

- [x] **Step 2: Add script to type-check coverage**

Append `scripts/release_artifact_manifest.py` to the `make type-check` mypy invocation and assert it in `tests/test_quality_command_contracts.py`.

- [x] **Step 3: Run focused tests**

Run:

```bash
uv run python -m pytest tests/test_release_artifact_manifest.py tests/test_quality_command_contracts.py::test_makefile_typecheck_covers_full_package_and_release_health_modules -q
```

Expected: all selected tests pass.

### Task 3: Wire Release Workflow And Docs

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `docs/release-verification.md`
- Modify: `docs/release-operator-checklist.md`
- Modify: `tests/test_ci_workflow.py`
- Modify: `tests/test_release_version_policy.py`

- [x] **Step 1: Add workflow contract tests**

Assert the release workflow runs `scripts/release_artifact_manifest.py`, attaches `dist/SHA256SUMS.txt`, and docs/checklist mention the manifest.

- [x] **Step 2: Update workflow and docs**

Generate the checksum manifest after `uv build` and include `dist/SHA256SUMS.txt` in `gh release create`. Document checking the manifest in the release verification docs and operator checklist.

- [x] **Step 3: Run workflow/docs tests**

Run:

```bash
uv run python -m pytest tests/test_ci_workflow.py::test_release_workflow_verifies_and_attaches_package_artifacts tests/test_ci_workflow.py::test_release_docs_explain_github_release_publishing tests/test_release_version_policy.py::test_release_operator_checklist_covers_end_to_end_release_flow -q
```

Expected: all selected tests pass.

### Task 4: Verify End To End

**Files:**
- No additional edits expected.

- [x] **Step 1: Run local manifest generation against built artifacts**

Run:

```bash
rm -rf dist
uv build
uv run python scripts/release_artifact_manifest.py dist/*.tar.gz dist/*.whl
cat dist/SHA256SUMS.txt
```

Expected: exactly two digest lines, one for the wheel and one for the source distribution.

- [x] **Step 2: Run full verification**

Run:

```bash
make verify
```

Expected: lint, format, mypy, docs drift, pytest, build, and release health pass.
