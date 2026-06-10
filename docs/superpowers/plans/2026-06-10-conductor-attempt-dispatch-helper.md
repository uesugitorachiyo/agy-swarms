# Conductor Attempt Dispatch Helper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the conductor's single-attempt node dispatch logic from `Conductor._run_node` into a focused helper module.

**Architecture:** Keep the retry loop, accounting, fallback accounting, checkpointing, and report construction owned by `Conductor`. Move only the role-based attempt dispatch for reducer, command, review, and worker nodes into `agy_swarms/conductor_dispatch.py`, passing conductor-owned mutable dependencies through a small dataclass. Preserve `Conductor._run_node` as a thin compatibility wrapper.

**Tech Stack:** Python 3.11, dataclasses, pytest, mypy, existing `conductor_*` helper modules.

---

### Task 1: Pin the New Helper Contract

**Files:**
- Modify: `tests/test_conductor_helpers.py`

- [x] **Step 1: Write the failing import/behavior test**

Add `test_conductor_dispatch_helper_is_importable` to `tests/test_conductor_helpers.py`. It should import `RunNodeAttemptDeps` and `run_node_attempt` from `agy_swarms.conductor_dispatch`, build a reducer node with one succeeded child result, and assert that the helper returns a succeeded zero-token reducer envelope.

- [x] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run python -m pytest tests/test_conductor_helpers.py::test_conductor_dispatch_helper_is_importable -q
```

Expected: `ModuleNotFoundError: No module named 'agy_swarms.conductor_dispatch'`.

### Task 2: Implement the Helper and Delegate

**Files:**
- Create: `agy_swarms/conductor_dispatch.py`
- Modify: `agy_swarms/conductor.py`
- Modify: `tests/test_quality_command_contracts.py`

- [x] **Step 1: Create `RunNodeAttemptDeps` and `run_node_attempt`**

Move the body of `Conductor._run_node` into `run_node_attempt`, with conductor state supplied through `RunNodeAttemptDeps`.

- [x] **Step 2: Make `Conductor._run_node` delegate**

Replace the role-dispatch body with construction of `RunNodeAttemptDeps` and a call to `run_node_attempt`.

- [x] **Step 3: Update architecture contract tests**

Add `agy_swarms/conductor_dispatch.py` to the documented helper-boundary assertion in `tests/test_quality_command_contracts.py`.

- [x] **Step 4: Run focused tests**

Run:

```bash
uv run python -m pytest tests/test_conductor_helpers.py::test_conductor_dispatch_helper_is_importable tests/test_quality_command_contracts.py::test_architecture_doc_describes_command_conductor_and_helper_boundaries -q
```

Expected: both tests pass.

### Task 3: Verify Existing Behavior

**Files:**
- No additional edits expected.

- [x] **Step 1: Run conductor-focused tests**

Run:

```bash
uv run python -m pytest tests/test_conductor.py tests/test_conductor_helpers.py tests/test_conductor_test_node.py tests/test_conductor_fallback.py tests/test_hybrid_review.py -q
```

Expected: all selected tests pass.

- [x] **Step 2: Run full verification**

Run:

```bash
make verify
```

Expected: lint, format, mypy, docs drift, pytest, build, and release health pass.
