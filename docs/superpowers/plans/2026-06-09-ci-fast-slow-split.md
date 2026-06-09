# CI Fast Slow Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve CI feedback by making fast checks and slow release-health probes separate, cached jobs.

**Architecture:** Promote a `verify-fast` Make target for lint, format, full-package mypy, release-doc drift, tests, and build. Keep `verify` as the full local facade by composing `verify-fast` plus `release-health`. Update GitHub Actions to run `verify-fast` on the OS matrix and run slow release health once on Ubuntu after fast checks.

**Tech Stack:** GitHub Actions, Make, uv, pytest.

---

### Task 1: Pin The Desired CI Contract With Tests

**Files:**
- Modify: `tests/test_ci_workflow.py`
- Modify: `tests/test_quality_command_contracts.py`

- [x] **Step 1: Add failing contract assertions**

Assert that:

```text
- CI setup-uv steps cache against uv.lock
- the OS matrix job runs make verify-fast
- CI has a dedicated release-health job that runs make release-health
- the release-health job depends on fast checks
- Makefile exposes verify-fast and keeps verify composed from verify-fast plus release-health
```

- [x] **Step 2: Run the focused tests**

Run:

```bash
uv run python -m pytest tests/test_ci_workflow.py tests/test_quality_command_contracts.py -q
```

Expected: fail before implementation.

### Task 2: Split Make Targets And CI Jobs

**Files:**
- Modify: `Makefile`
- Modify: `.github/workflows/ci.yml`

- [x] **Step 1: Add `verify-fast` target**

Set:

```make
verify-fast: lint format-check type-check verify-docs test build
verify: verify-fast release-health
```

- [x] **Step 2: Update CI jobs**

Change the matrix verification job to `fast-checks` and run `make verify-fast`. Add a `release-health` Ubuntu job with `needs: fast-checks` that installs dependencies and runs `make release-health`. Add `cache-dependency-glob: uv.lock` to uv setup steps.

### Task 3: Verify And Publish

**Files:**
- Read: project source and tests

- [x] **Step 1: Run focused tests**

Run:

```bash
uv run python -m pytest tests/test_ci_workflow.py tests/test_quality_command_contracts.py -q
```

Expected: pass.

- [x] **Step 2: Run full verification**

Run:

```bash
make verify
```

Expected: Ruff, format, full-package mypy, release-doc drift, pytest, build, and release-health all pass.

- [ ] **Step 3: Commit and push**

Run:

```bash
git add .github/workflows/ci.yml Makefile tests/test_ci_workflow.py tests/test_quality_command_contracts.py docs/superpowers/plans/2026-06-09-ci-fast-slow-split.md
git commit -m "ci: split fast checks from release health"
git push
```

Expected: PR #2 updates with one focused CI commit.
