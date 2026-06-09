# Conductor Checkpoint Side Effects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move checkpoint journal construction and cache adoption mechanics out of `agy_swarms/conductor.py` without changing resume behavior.

**Architecture:** Keep orchestration decisions in `Conductor`, but move pure checkpoint/resume mechanics into `agy_swarms/conductor_checkpointing.py`. The helper module owns terminal cache filtering, runtime hydration from journal hits, node barrier `JournalEntry` creation, deterministic pipeline stage keys, and pipeline stage journal entries.

**Tech Stack:** Python dataclasses/enums, pytest, mypy, Ruff, existing `Checkpoint` and `JournalEntry` contracts.

---

### Task 1: Add Checkpoint Helper Behavior Tests

**Files:**
- Modify: `tests/test_conductor.py`

- [ ] **Step 1: Write the failing test**

Add assertions to `test_checkpointing_helper_is_importable` importing `cached_terminal_envelope`, `cached_success_envelope`, `build_node_journal_entry`, `build_pipeline_journal_entry`, `pipeline_stage_key`, and `adopt_cached_runtime`. Build a `JournalEntry` from a `NodeSpec`, `NodeRuntimeState`, `Epoch`, and `ResultEnvelope`, assert key/status/attempt/budget fields match, assert failed cache hits are accepted for node cache but rejected for pipeline cache, and assert pipeline keys change when `epoch_id` changes.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_checkpointing_helper_is_importable`
Expected: FAIL because the new helper functions are not exported yet.

### Task 2: Implement Checkpoint Helper Functions

**Files:**
- Modify: `agy_swarms/conductor_checkpointing.py`

- [ ] **Step 1: Add helper functions**

Implement:
- `cached_terminal_envelope(hit: JournalEntry | None) -> ResultEnvelope | None`
- `cached_success_envelope(hit: JournalEntry | None) -> ResultEnvelope | None`
- `adopt_cached_runtime(runtime: NodeRuntimeState, hit: JournalEntry) -> None`
- `build_node_journal_entry(node_id: str, node: NodeSpec, runtime: NodeRuntimeState, envelope: ResultEnvelope, epoch: Epoch) -> JournalEntry`
- `pipeline_stage_key(pipeline_id: str, index: int, stage_idx: int, n_stages: int, epoch_id: str) -> str`
- `build_pipeline_journal_entry(key: str, envelope: ResultEnvelope, epoch: Epoch) -> JournalEntry`

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_checkpointing_helper_is_importable`
Expected: PASS.

### Task 3: Wire Conductor Through Helpers

**Files:**
- Modify: `agy_swarms/conductor.py`

- [ ] **Step 1: Replace inline logic**

Use `cached_terminal_envelope` and `adopt_cached_runtime` in `_serve_from_cache`, `build_node_journal_entry` in `_checkpoint_barrier`, `pipeline_stage_key` in `_pipeline_key`, `cached_success_envelope` in `_pipeline_cache_lookup`, and `build_pipeline_journal_entry` in `_pipeline_journal`.

- [ ] **Step 2: Run focused behavior tests**

Run: `uv run python -m pytest -q tests/test_conductor.py tests/test_checkpoint.py`
Expected: PASS.

### Task 4: Type-Check the New Boundary

**Files:**
- Modify: `Makefile`
- Modify: `tests/test_quality_command_contracts.py`

- [ ] **Step 1: Write failing Makefile coverage assertion**

Assert `agy_swarms/conductor_checkpointing.py` appears in the `type-check` target.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/test_quality_command_contracts.py::test_makefile_typecheck_covers_cli_runner_and_release_health_modules`
Expected: FAIL because the checkpointing helper is not yet listed.

- [ ] **Step 3: Add helper to Makefile type-check target**

Append `agy_swarms/conductor_checkpointing.py` to the `uv run mypy --explicit-package-bases ...` command.

- [ ] **Step 4: Run type-check**

Run: `make type-check`
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
