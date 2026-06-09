# Conductor Test Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce duplicated conductor test helpers by extracting shared fixtures into a focused support module.

**Architecture:** Add `tests/conductor_support.py` for reusable conductor test primitives: the large budget limit, epoch factory, envelope factory, fanout graph, scripted fanout adapter, counting adapter wrapper, fake scripted-envelope adapter, and single-node graph helper. Update conductor test modules to import these helpers while leaving scenario-specific classes local.

**Tech Stack:** Python 3.11, pytest, Ruff, mypy.

---

### Task 1: Pin The Support Module Contract

**Files:**
- Modify: `tests/test_quality_command_contracts.py`

- [x] **Step 1: Add failing contract assertions**

Assert that:

```text
- tests/conductor_support.py exists
- it exports LIMIT, epoch, envelope, fanout_graph, scripted_fanout_adapter, CountingAdapter, FakeAdapter, and single_graph
- repeated local FakeAdapter and _epoch helper definitions are absent from the main conductor behavior tests
```

- [x] **Step 2: Run the focused contract test**

Run:

```bash
uv run python -m pytest tests/test_quality_command_contracts.py -q
```

Expected: fail until the support module exists and tests are updated.

### Task 2: Extract Shared Helpers

**Files:**
- Create: `tests/conductor_support.py`
- Modify: `tests/test_conductor.py`
- Modify: `tests/test_ac1_integration.py`
- Modify: `tests/test_conductor_reducers.py`
- Modify: `tests/test_conductor_test_node.py`
- Modify: `tests/test_conductor_fallback.py`
- Modify: `tests/test_conductor_integrated_failure_paths.py`

- [x] **Step 1: Create shared support helpers**

Move generic helper behavior into `tests/conductor_support.py` without changing runtime behavior.

- [x] **Step 2: Update tests to import shared helpers**

Alias imports where useful so existing test bodies remain readable, for example:

```python
from tests.conductor_support import LIMIT as _LIMIT
from tests.conductor_support import epoch as _epoch
```

### Task 3: Verify And Publish

**Files:**
- Read: project source and tests

- [x] **Step 1: Run focused conductor tests**

Run:

```bash
uv run python -m pytest tests/test_conductor.py tests/test_ac1_integration.py tests/test_conductor_reducers.py tests/test_conductor_test_node.py tests/test_conductor_fallback.py tests/test_conductor_integrated_failure_paths.py tests/test_quality_command_contracts.py -q
```

- [x] **Step 2: Run full verification**

Run:

```bash
make verify
```

- [ ] **Step 3: Commit, push, and refresh PR evidence**

Run:

```bash
git add tests/conductor_support.py tests/test_conductor.py tests/test_ac1_integration.py tests/test_conductor_reducers.py tests/test_conductor_test_node.py tests/test_conductor_fallback.py tests/test_conductor_integrated_failure_paths.py tests/test_quality_command_contracts.py docs/superpowers/plans/2026-06-09-conductor-test-support.md
git commit -m "test: extract conductor test support helpers"
git push
make pr-verification PR_NUMBER=2
```

Expected: PR #2 updates with one focused test-support commit and current verification evidence.
