# Inspect Typecheck And Review Dispatch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Continue repo hardening by splitting the inspect command module, adding limited type checking, adding docs verification to the Makefile facade, and extracting conductor review dispatch.

**Architecture:** Keep public CLI behavior stable. Move inspect/resume report helpers into small command modules, add a mypy target over the newly split modules, add `verify-docs` to Makefile, and move reviewer/closer dispatch logic from `Conductor._run_node()` into `agy_swarms.conductor_review`.

**Tech Stack:** Python 3.11+, uv, pytest, ruff, mypy, Make.

---

### Task 1: Split Inspect Command Module

**Files:**
- Create: `agy_swarms/commands/report_summary.py`
- Create: `agy_swarms/commands/resume.py`
- Create: `agy_swarms/commands/inspect_bundle.py`
- Modify: `agy_swarms/commands/inspect.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing import test**

```python
def test_inspect_command_helpers_are_split():
    from agy_swarms.commands.report_summary import summarize_run_report
    from agy_swarms.commands.resume import cmd_resume
    from agy_swarms.commands.inspect_bundle import inspect_review_bundle
```

- [ ] **Step 2: Verify red**

Run: `uv run python -m pytest -q tests/test_cli.py::test_inspect_command_helpers_are_split`
Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Move helpers**

Move report loading/summarizing to `report_summary.py`, resume command to `resume.py`, and bundle helpers to `inspect_bundle.py`. Keep `inspect.py` as the checkpoint/file command plus imports.

- [ ] **Step 4: Verify green**

Run: `uv run python -m pytest -q tests/test_cli.py tests/test_local_runner_cli.py`
Expected: PASS.

### Task 2: Limited Type Checking

**Files:**
- Modify: `pyproject.toml`
- Modify: `Makefile`
- Test: `tests/test_quality_command_contracts.py`

- [ ] **Step 1: Write failing test**

```python
def test_makefile_exposes_typecheck_target():
    assert "type-check:" in Path("Makefile").read_text()
```

- [ ] **Step 2: Verify red**

Run: `uv run python -m pytest -q tests/test_quality_command_contracts.py::test_makefile_exposes_typecheck_target`
Expected: FAIL because the target is absent.

- [ ] **Step 3: Add mypy**

Add `mypy` to dev dependencies and a `type-check` Makefile target that checks only the newly split command/conductor helper modules.

- [ ] **Step 4: Verify green**

Run: `make type-check` and `uv run python -m pytest -q tests/test_quality_command_contracts.py`
Expected: PASS.

### Task 3: Verify Docs Facade

**Files:**
- Modify: `Makefile`
- Test: `tests/test_quality_command_contracts.py`

- [ ] **Step 1: Write failing test**

```python
def test_makefile_exposes_verify_docs_target():
    assert "verify-docs:" in Path("Makefile").read_text()
```

- [ ] **Step 2: Verify red**

Run: `uv run python -m pytest -q tests/test_quality_command_contracts.py::test_makefile_exposes_verify_docs_target`
Expected: FAIL because the target is absent.

- [ ] **Step 3: Add target**

Add `verify-docs` target that runs `scripts/rewrite_release_health_docs.py` and `git diff --exit-code docs/release-verification.md`.

- [ ] **Step 4: Verify green**

Run: `make verify-docs`
Expected: PASS.

### Task 4: Review Dispatch Extraction

**Files:**
- Create: `agy_swarms/conductor_review.py`
- Modify: `agy_swarms/conductor.py`
- Test: `tests/test_conductor.py`

- [ ] **Step 1: Write failing import test**

```python
def test_review_dispatch_helper_is_importable():
    from agy_swarms.conductor_review import run_review_node
```

- [ ] **Step 2: Verify red**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_review_dispatch_helper_is_importable`
Expected: FAIL because module does not exist.

- [ ] **Step 3: Extract helper**

Move reviewer/closer route dispatch from `_run_node()` into `run_review_node()`.

- [ ] **Step 4: Verify green**

Run: `uv run python -m pytest -q tests/test_conductor.py tests/test_hybrid_review.py`
Expected: PASS.

### Final Verification

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run python -m pytest -q`
- [ ] `uv build`
- [ ] `uv run python scripts/release_health.py`
