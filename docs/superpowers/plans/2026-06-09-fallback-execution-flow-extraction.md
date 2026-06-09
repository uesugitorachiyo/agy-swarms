# Fallback Execution Flow Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the repeated fallback dispatch attempt mechanics out of `agy_swarms/conductor.py`.

**Architecture:** Keep fallback policy, reservation, ledger commit, and blocker decisions in `Conductor`. Move the common fallback execution mechanics into `agy_swarms/conductor_fallback.py`: increment attempt, attach reservation id, run fallback callable, stamp the envelope, compute actual budget dimensions, and update runtime error class.

**Tech Stack:** Python helper dataclass, pytest red-green tests, Ruff, mypy, existing conductor fallback tests.

---

### Task 1: Add Fallback Execution Helper Contract

**Files:**
- Modify: `tests/test_conductor.py`

- [ ] **Step 1: Write the failing test**

Extend `test_fallback_helper_is_importable` to import `execute_fallback_run`. Build a fake admission with `reservation_id`, a `NodeRuntimeState`, a `NodeSpec`, a fallback callable returning a `ResultEnvelope`, and a stamp callable. Assert the helper increments attempt, sets reservation id, returns the envelope, computes billable tokens from output plus thinking, and copies envelope error class to runtime.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_fallback_helper_is_importable`
Expected: FAIL because `execute_fallback_run` is not exported yet.

### Task 2: Implement Fallback Execution Helper

**Files:**
- Modify: `agy_swarms/conductor_fallback.py`

- [ ] **Step 1: Add helper result dataclass and function**

Add `FallbackRunResult(envelope: ResultEnvelope, actual: Dims)` and `execute_fallback_run(...)`. The helper accepts `node`, `runtime`, `reservation_id`, `run`, and `stamp` callables.

- [ ] **Step 2: Run helper test**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_fallback_helper_is_importable`
Expected: PASS.

### Task 3: Wire Conductor Through Helper

**Files:**
- Modify: `agy_swarms/conductor.py`

- [ ] **Step 1: Replace duplicated fallback run sequences**

Use `execute_fallback_run` in both review fallback and worker fallback branches. Keep ledger commit, budget consumption, review-budget events, and adapter state changes in `Conductor`.

- [ ] **Step 2: Reuse `model_switch_event` for worker fallback**

Replace the worker fallback inline `model_switch` dictionary with `model_switch_event`.

- [ ] **Step 3: Run focused fallback tests**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_fallback_helper_is_importable tests/test_conductor_fallback.py tests/test_hybrid_review.py`
Expected: PASS.

### Task 4: Full Verification

**Files:**
- No code edits.

- [ ] **Step 1: Run verification commands**

Run:
- `uv run ruff check .`
- `uv run ruff format --check .`
- `make type-check`
- `uv run python -m pytest -q`
- `uv build`
- `uv run python scripts/release_health.py`

Expected: all commands exit 0.
