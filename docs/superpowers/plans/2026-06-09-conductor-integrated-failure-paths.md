# Conductor Integrated Failure Paths Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add full-run integration coverage for adapter crashes, fallback routing, checkpoint replay, and budget accounting.

**Architecture:** Keep the tests above helper-level contracts by driving the real `Conductor`, `BudgetLedger`, `Checkpoint`, and scripted fallback adapter together. Do not change production behavior unless the integration tests expose an actual gap.

**Tech Stack:** Python 3.11, pytest, uv, mypy.

---

### Task 1: Add Crash/Fallback/Resume Integration Tests

**Files:**
- Create: `tests/test_conductor_integrated_failure_paths.py`

- [x] **Step 1: Write failing integration tests**

Add tests that:

```text
- dispatch a worker whose primary adapter raises RuntimeError
- route the deterministic UNKNOWN failure to a fallback adapter
- assert the fallback result succeeds, records a model_switch, and commits billable output tokens
- reopen the checkpoint and assert resume serves the fallback result without redispatch
- dispatch a no-fallback crash graph and assert failed node, skipped dependent, and committed sibling states
```

- [x] **Step 2: Run the new tests**

Run:

```bash
uv run python -m pytest tests/test_conductor_integrated_failure_paths.py -q
```

Expected: pass if the refactored conductor already preserves the integrated behavior; otherwise fail with a production gap to fix.

### Task 2: Verify The Full Repository

**Files:**
- Read: project source and tests

- [x] **Step 1: Run full verification**

Run:

```bash
make verify
```

Expected: Ruff, format check, full-package mypy, release docs drift, pytest, build, and release health all pass.

### Task 3: Publish PR Update

**Files:**
- Commit: `tests/test_conductor_integrated_failure_paths.py`
- Commit: `docs/superpowers/plans/2026-06-09-conductor-integrated-failure-paths.md`

- [ ] **Step 1: Commit and push**

Run:

```bash
git add tests/test_conductor_integrated_failure_paths.py docs/superpowers/plans/2026-06-09-conductor-integrated-failure-paths.md
git commit -m "test: cover integrated conductor failure paths"
git push
```

Expected: PR #2 updates with one focused test commit.
