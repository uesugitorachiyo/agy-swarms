# Conductor Drift Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract conductor drift-check orchestration and report copying into `agy_swarms/conductor_drift.py`.

**Architecture:** Keep `validate.check_drift` as the source of truth for per-key drift comparison and abort rules. Add a conductor-facing helper that handles optional lockfile inputs and a report helper that defensively copies drift records before `RunReport` construction.

**Tech Stack:** Python helper module, existing `Lockfile` and `DriftRecord` dataclasses, pytest red-green tests, Ruff, mypy.

---

### Task 1: Add Drift Helper Contract

**Files:**
- Modify: `tests/test_conductor.py`

- [ ] **Step 1: Write the failing test**

Add `test_drift_helper_is_importable` importing `collect_drift_records` and `report_drift_records`. Assert missing lockfiles return `[]`, allow-drift model-pin mismatch returns a `DriftRecord`, and `report_drift_records` returns a defensive copy.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_drift_helper_is_importable`
Expected: FAIL because `agy_swarms.conductor_drift` does not exist.

### Task 2: Implement Drift Helper

**Files:**
- Create: `agy_swarms/conductor_drift.py`

- [ ] **Step 1: Implement helper functions**

Add `collect_drift_records(locked: Lockfile | None, actual: Lockfile | None, *, allow_drift: bool) -> list[DriftRecord]` and `report_drift_records(records: Sequence[DriftRecord]) -> list[DriftRecord]`.

- [ ] **Step 2: Run helper test**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_drift_helper_is_importable`
Expected: PASS.

### Task 3: Wire Conductor Through Helper

**Files:**
- Modify: `agy_swarms/conductor.py`

- [ ] **Step 1: Replace inline drift logic**

Import `collect_drift_records` and `report_drift_records`. Change `_check_drift` to assign from `collect_drift_records(...)`. Change `_build_report` to pass `report_drift_records(self._drift_records)`.

- [ ] **Step 2: Run focused drift tests**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_drift_helper_is_importable tests/test_drift_recording.py tests/test_lockfile_drift_ac6.py`
Expected: PASS.

### Task 4: Add Type-Check Coverage

**Files:**
- Modify: `Makefile`
- Modify: `tests/test_quality_command_contracts.py`

- [ ] **Step 1: Add failing coverage assertion**

Assert `agy_swarms/conductor_drift.py` appears in the Makefile `type-check` target.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/test_quality_command_contracts.py::test_makefile_typecheck_covers_cli_runner_and_release_health_modules`
Expected: FAIL until the Makefile includes the helper.

- [ ] **Step 3: Add helper to Makefile type-check**

Append `agy_swarms/conductor_drift.py` to the `type-check` target.

- [ ] **Step 4: Run `make type-check`**

Expected: PASS.

### Task 5: Full Verification

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
