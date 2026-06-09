# Conductor Helper Test Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move conductor helper contract tests out of `tests/test_conductor.py` into a focused `tests/test_conductor_helpers.py` module.

**Architecture:** Keep `tests/test_conductor.py` focused on conductor classification, agent, run, resume, and pipeline behavior. Put import/contract tests for `agy_swarms/conductor_*.py` helper modules in `tests/test_conductor_helpers.py`.

**Tech Stack:** Pytest, existing conductor helper modules, Ruff.

---

### Task 1: Add Split Contract

**Files:**
- Modify: `tests/test_quality_command_contracts.py`

- [ ] **Step 1: Write failing contract**

Add `test_conductor_helper_contracts_live_in_focused_test_module`. It should assert `tests/test_conductor_helpers.py` exists, contains representative helper contract names, and `tests/test_conductor.py` no longer contains `_helper_is_importable`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/test_quality_command_contracts.py::test_conductor_helper_contracts_live_in_focused_test_module`
Expected: FAIL because the focused helper test file does not exist yet.

### Task 2: Move Helper Tests

**Files:**
- Create: `tests/test_conductor_helpers.py`
- Modify: `tests/test_conductor.py`

- [ ] **Step 1: Create focused helper test file**

Move tests named `test_*_helper_is_importable` plus `test_conductor_report_module_exports_report_shapes` into `tests/test_conductor_helpers.py`. Include a local `_env(...)` helper for envelope construction.

- [ ] **Step 2: Remove moved tests and unused imports**

Remove moved tests from `tests/test_conductor.py`. Drop imports only used by helper tests.

- [ ] **Step 3: Run focused tests**

Run: `uv run python -m pytest -q tests/test_conductor_helpers.py tests/test_conductor.py tests/test_quality_command_contracts.py::test_conductor_helper_contracts_live_in_focused_test_module`
Expected: PASS.

### Task 3: Full Verification

**Files:**
- No additional edits.

- [ ] **Step 1: Run verification commands**

Run:
- `uv run ruff check .`
- `uv run ruff format --check .`
- `make type-check`
- `uv run python -m pytest -q`
- `uv build`
- `uv run python scripts/release_health.py`

Expected: all commands exit 0.
