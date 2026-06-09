# Conductor Accounting Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract repeated conductor actual-usage and ledger-commit mechanics into `agy_swarms/conductor_budget.py`.

**Architecture:** Keep reservation policy in `Conductor` because it depends on model routing, fallback state, and node role. Move the mechanical post-dispatch accounting flow into helpers: compute actual `Dims` from a `ResultEnvelope`, commit actual usage to a ledger, and update runtime consumed budget.

**Tech Stack:** Python helper functions, existing `BudgetLedger`/`Dims`, pytest red-green tests, Ruff, mypy.

---

### Task 1: Add Accounting Helper Contract

**Files:**
- Modify: `tests/test_conductor.py`

- [ ] **Step 1: Write the failing test**

Extend `test_conductor_budget_helpers_are_importable` to import `actual_from_envelope` and `commit_actual_usage`. Build a `ResultEnvelope` with `output`, `thinking`, and `cost_usd`, assert `actual_from_envelope` returns the expected `Dims`, then use a fake ledger and runtime object to assert `commit_actual_usage` calls `ledger.commit(...)` and accumulates runtime budget.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_conductor_budget_helpers_are_importable`
Expected: FAIL because the new helpers are not exported yet.

### Task 2: Implement Accounting Helpers

**Files:**
- Modify: `agy_swarms/conductor_budget.py`

- [ ] **Step 1: Add helper functions**

Implement `actual_from_envelope(envelope: ResultEnvelope) -> Dims` and `commit_actual_usage(...) -> Dims`.

- [ ] **Step 2: Run helper test**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_conductor_budget_helpers_are_importable`
Expected: PASS.

### Task 3: Wire Conductor Through Helpers

**Files:**
- Modify: `agy_swarms/conductor.py`

- [ ] **Step 1: Replace duplicated accounting code**

Use `actual_from_envelope` and `commit_actual_usage` in Codex batch, normal dispatch, and both fallback commit branches.

- [ ] **Step 2: Run focused tests**

Run: `uv run python -m pytest -q tests/test_conductor.py tests/test_conductor_fallback.py tests/test_hybrid_review.py`
Expected: PASS.

### Task 4: Full Verification

**Files:**
- No additional code edits.

- [ ] **Step 1: Run verification commands**

Run:
- `uv run ruff check .`
- `uv run ruff format --check .`
- `make type-check`
- `uv run python -m pytest -q`
- `uv build`
- `uv run python scripts/release_health.py`

Expected: all commands exit 0.
