# Pipeline Execution Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move per-item pipeline execution out of `agy_swarms/conductor.py` into `agy_swarms/conductor_pipeline.py`.

**Architecture:** Keep public `Conductor.pipeline(...)` as the orchestration entrypoint, but delegate each item’s staged execution to a helper function. The helper receives callbacks for key generation, cache lookup, journaling, and envelope classification so checkpoint/epoch details remain owned by `Conductor`.

**Tech Stack:** Python callback helper, existing `PipelineItemResult`, pytest red-green tests, Ruff, mypy.

---

### Task 1: Add Pipeline Helper Contract

**Files:**
- Modify: `tests/test_conductor.py`

- [ ] **Step 1: Write the failing test**

Add `test_pipeline_helper_is_importable` importing `run_pipeline_item` from `agy_swarms.conductor_pipeline`. Exercise a cached first stage and a fresh second stage, assert the cached stage is not called, the fresh stage receives previous artifact, the journal callback is called with the second-stage key, and the returned `PipelineItemResult` reports success with two completed stages.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_pipeline_helper_is_importable`
Expected: FAIL because `agy_swarms.conductor_pipeline` does not exist.

### Task 2: Implement Pipeline Helper

**Files:**
- Create: `agy_swarms/conductor_pipeline.py`

- [ ] **Step 1: Implement `run_pipeline_item`**

The helper should copy the current `_run_pipeline_item` logic: iterate stages, check cache first, set `node_id`/`idempotency_key`, return a failed `PipelineItemResult` with blocker on classified failure, journal each successful fresh stage, and return a successful result after all stages.

- [ ] **Step 2: Run helper test**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_pipeline_helper_is_importable`
Expected: PASS.

### Task 3: Wire Conductor Through Helper

**Files:**
- Modify: `agy_swarms/conductor.py`

- [ ] **Step 1: Import and call helper**

Import `run_pipeline_item`. Change `Conductor.pipeline(...)` to call it directly for each item. Remove `_run_pipeline_item` from `Conductor`.

- [ ] **Step 2: Run focused pipeline tests**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_pipeline_helper_is_importable tests/test_conductor.py::test_pipeline_streams_items_through_stages_in_order tests/test_conductor.py::test_pipeline_isolates_one_failing_item tests/test_conductor.py::test_pipeline_crash_resume_skips_committed_items`
Expected: PASS.

### Task 4: Add Type-Check Coverage

**Files:**
- Modify: `Makefile`
- Modify: `tests/test_quality_command_contracts.py`

- [ ] **Step 1: Add failing coverage assertion**

Assert `agy_swarms/conductor_pipeline.py` appears in the Makefile `type-check` target.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/test_quality_command_contracts.py::test_makefile_typecheck_covers_cli_runner_and_release_health_modules`
Expected: FAIL until the Makefile includes the helper.

- [ ] **Step 3: Add helper to Makefile type-check**

Append `agy_swarms/conductor_pipeline.py` to the `type-check` target.

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
