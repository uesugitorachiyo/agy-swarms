# Fallback Checkpoint And CI Verify Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Continue shrinking `conductor.py`, widen type-check coverage safely, and keep CI aligned with the local Makefile verification facade.

**Architecture:** Extract fallback decision helpers into `agy_swarms.conductor_fallback`, extract checkpoint/cache helper logic into `agy_swarms.conductor_checkpointing`, expand `make type-check` to cover stable newly split modules, and add a CI job that runs `make verify`.

**Tech Stack:** Python 3.11+, uv, pytest, ruff, mypy, Make, GitHub Actions.

---

### Task 1: Fallback Helper Extraction

**Files:**
- Create: `agy_swarms/conductor_fallback.py`
- Modify: `agy_swarms/conductor.py`
- Test: `tests/test_conductor.py`

- [ ] **Step 1: Write failing import test**

```python
def test_fallback_helper_is_importable():
    from agy_swarms.conductor_fallback import next_review_fallback_adapter
```

- [ ] **Step 2: Verify red**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_fallback_helper_is_importable`
Expected: FAIL because module does not exist.

- [ ] **Step 3: Extract helper**

Move reviewer/closer fallback adapter selection and event payload construction into `conductor_fallback.py`. Keep budget reservation and mutation in `Conductor`.

- [ ] **Step 4: Verify green**

Run: `uv run python -m pytest -q tests/test_conductor.py tests/test_review_escalation.py`
Expected: PASS.

### Task 2: Checkpoint/Cache Helper Extraction

**Files:**
- Create: `agy_swarms/conductor_checkpointing.py`
- Modify: `agy_swarms/conductor.py`
- Test: `tests/test_conductor.py`

- [ ] **Step 1: Write failing import test**

```python
def test_checkpointing_helper_is_importable():
    from agy_swarms.conductor_checkpointing import cached_result_is_valid
```

- [ ] **Step 2: Verify red**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_checkpointing_helper_is_importable`
Expected: FAIL because module does not exist.

- [ ] **Step 3: Extract helper**

Move cache-hit validation into `cached_result_is_valid()`. Keep checkpoint side effects in `Conductor`.

- [ ] **Step 4: Verify green**

Run: `uv run python -m pytest -q tests/test_conductor.py tests/test_checkpoint.py`
Expected: PASS.

### Task 3: Expand Type Checking

**Files:**
- Modify: `Makefile`
- Test: `tests/test_quality_command_contracts.py`

- [ ] **Step 1: Write failing target test**

```python
def test_typecheck_covers_core_split_modules():
    assert "agy_swarms/cli.py" in makefile
    assert "agy_swarms/local_runner.py" in makefile
```

- [ ] **Step 2: Verify red**

Run: `uv run python -m pytest -q tests/test_quality_command_contracts.py::test_typecheck_covers_core_split_modules`
Expected: FAIL until Makefile expands the module list.

- [ ] **Step 3: Expand target**

Add stable modules to `make type-check`: `agy_swarms/cli.py`, `agy_swarms/local_runner.py`, and release-health scripts if mypy-clean.

- [ ] **Step 4: Verify green**

Run: `make type-check`
Expected: PASS.

### Task 4: CI Make Verify Job

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/test_ci_workflow.py`

- [ ] **Step 1: Write failing workflow test**

```python
def test_ci_runs_make_verify():
    assert "make-verify:" in workflow
    assert "make verify" in workflow
```

- [ ] **Step 2: Verify red**

Run: `uv run python -m pytest -q tests/test_ci_workflow.py::test_ci_runs_make_verify`
Expected: FAIL until CI job exists.

- [ ] **Step 3: Add CI job**

Add an Ubuntu job that syncs dev+gemini dependencies and runs `make verify`.

- [ ] **Step 4: Verify green**

Run: `uv run python -m pytest -q tests/test_ci_workflow.py`
Expected: PASS.

### Final Verification

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `make type-check`
- [ ] `uv run python -m pytest -q`
- [ ] `uv build`
- [ ] `uv run python scripts/release_health.py`
