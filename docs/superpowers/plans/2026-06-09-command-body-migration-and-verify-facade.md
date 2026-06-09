# Command Body Migration And Verify Facade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the command-module split, add docs drift enforcement, add a contributor-friendly verification facade, and continue conductor extraction.

**Architecture:** Move real command implementations into grouped command modules, keep `_legacy.py` as compatibility re-exports only, extract adapter crash-envelope construction from `conductor.py`, add a CI step that fails when release docs are not regenerated, and add a Makefile with stable verification targets.

**Tech Stack:** Python 3.11+, uv, pytest, ruff, GitHub Actions, Make.

---

### Task 1: Move Command Bodies

**Files:**
- Modify: `agy_swarms/commands/run.py`
- Modify: `agy_swarms/commands/preflight.py`
- Modify: `agy_swarms/commands/inspect.py`
- Modify: `agy_swarms/commands/review.py`
- Modify: `agy_swarms/commands/install.py`
- Modify: `agy_swarms/commands/_legacy.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing test**

```python
def test_grouped_command_modules_do_not_delegate_to_legacy():
    import inspect
    import agy_swarms.commands.run as run
    assert "._legacy" not in inspect.getsource(run)
```

- [ ] **Step 2: Verify red**

Run: `uv run python -m pytest -q tests/test_cli.py::test_grouped_command_modules_do_not_delegate_to_legacy`
Expected: FAIL because modules currently import `_legacy`.

- [ ] **Step 3: Move command bodies**

Move each command group into its module. Replace `_legacy.py` with re-exports from grouped modules.

- [ ] **Step 4: Verify green**

Run: `uv run python -m pytest -q tests/test_cli.py tests/test_local_runner_cli.py tests/test_agy_handoff_guardrails.py`
Expected: PASS.

### Task 2: Conductor Adapter Helper

**Files:**
- Create: `agy_swarms/conductor_adapters.py`
- Modify: `agy_swarms/conductor.py`
- Test: `tests/test_conductor.py`

- [ ] **Step 1: Write failing test**

```python
def test_adapter_crash_envelope_helper_is_importable():
    from agy_swarms.conductor_adapters import adapter_crash_envelope
```

- [ ] **Step 2: Verify red**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_adapter_crash_envelope_helper_is_importable`
Expected: FAIL because module does not exist.

- [ ] **Step 3: Extract helper**

Move repeated adapter crash envelope construction into `adapter_crash_envelope()`.

- [ ] **Step 4: Verify green**

Run: `uv run python -m pytest -q tests/test_conductor.py`
Expected: PASS.

### Task 3: Release Docs Drift Check

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/test_ci_workflow.py`

- [ ] **Step 1: Write failing test**

```python
def test_ci_checks_release_docs_probe_drift():
    assert "rewrite_release_health_docs.py" in workflow
    assert "git diff --exit-code docs/release-verification.md" in workflow
```

- [ ] **Step 2: Verify red**

Run: `uv run python -m pytest -q tests/test_ci_workflow.py`
Expected: FAIL because CI does not run the drift check.

- [ ] **Step 3: Add CI step**

Run the rewrite script and fail on docs diff.

- [ ] **Step 4: Verify green**

Run: `uv run python -m pytest -q tests/test_ci_workflow.py`
Expected: PASS.

### Task 4: Verification Facade

**Files:**
- Create: `Makefile`
- Create/Modify: `tests/test_quality_command_contracts.py`

- [ ] **Step 1: Write failing test**

```python
def test_makefile_exposes_verification_targets():
    text = Path("Makefile").read_text()
    assert "verify:" in text
```

- [ ] **Step 2: Verify red**

Run: `uv run python -m pytest -q tests/test_quality_command_contracts.py::test_makefile_exposes_verification_targets`
Expected: FAIL because Makefile is absent.

- [ ] **Step 3: Add Makefile**

Add `sync`, `lint`, `format-check`, `test`, `build`, `release-health`, and `verify` targets.

- [ ] **Step 4: Verify green**

Run: `uv run python -m pytest -q tests/test_quality_command_contracts.py`
Expected: PASS.

### Final Verification

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run python -m pytest -q`
- [ ] `uv build`
- [ ] `uv run python scripts/release_health.py`
