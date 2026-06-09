# Command Split And CI Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce command-handler file size, make release docs rewritable from the probe registry, add install-mode CI coverage, and continue conservative conductor extraction.

**Architecture:** Re-export command handlers from focused modules under `agy_swarms.commands`, keep `agy_swarms.cli.dispatch()` stable, add a docs rewrite script around `release_health_docs.render_probe_list()`, add CI jobs for package install modes, and move local command-node execution helpers out of `conductor.py`.

**Tech Stack:** Python 3.11+, uv, pytest, ruff, GitHub Actions.

---

### Task 1: Split Command Handlers

**Files:**
- Create: `agy_swarms/commands/run.py`
- Create: `agy_swarms/commands/preflight.py`
- Create: `agy_swarms/commands/inspect.py`
- Create: `agy_swarms/commands/review.py`
- Create: `agy_swarms/commands/install.py`
- Modify: `agy_swarms/commands/__init__.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing import test**

```python
def test_command_handlers_are_split_by_group():
    from agy_swarms.commands.run import cmd_run
    from agy_swarms.commands.preflight import cmd_preflight
    from agy_swarms.commands.inspect import cmd_inspect
    from agy_swarms.commands.review import cmd_review_route
    from agy_swarms.commands.install import cmd_pre_commit_install
```

- [ ] **Step 2: Verify red**

Run: `uv run python -m pytest -q tests/test_cli.py::test_command_handlers_are_split_by_group`
Expected: FAIL because the submodules do not exist.

- [ ] **Step 3: Move handlers**

Move handlers and their private helpers into focused modules. Re-export public `cmd_*` names from `agy_swarms.commands`.

- [ ] **Step 4: Verify green**

Run: `uv run python -m pytest -q tests/test_cli.py tests/test_local_runner_cli.py tests/test_agy_handoff_guardrails.py`
Expected: PASS.

### Task 2: Release Docs Rewrite Script

**Files:**
- Create: `scripts/rewrite_release_health_docs.py`
- Modify: `docs/release-verification.md`
- Test: `tests/test_release_health.py`

- [ ] **Step 1: Write failing test**

```python
def test_rewrite_release_docs_is_idempotent():
    from scripts.rewrite_release_health_docs import rewrite_release_health_probe_list
    assert rewrite_release_health_probe_list(docs_text) == docs_text
```

- [ ] **Step 2: Verify red**

Run: `uv run python -m pytest -q tests/test_release_health.py::test_rewrite_release_docs_is_idempotent`
Expected: FAIL because the script does not exist.

- [ ] **Step 3: Implement rewrite helper**

Replace content between fixed markdown markers with `render_probe_list()`.

- [ ] **Step 4: Verify green**

Run: `uv run python -m pytest -q tests/test_release_health.py`
Expected: PASS.

### Task 3: Install Mode CI Jobs

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/test_ci_workflow.py`

- [ ] **Step 1: Write failing test**

```python
def test_ci_has_package_install_mode_jobs():
    assert "package-install-modes" in workflow
    assert ".[gemini]" in workflow
```

- [ ] **Step 2: Verify red**

Run: `uv run python -m pytest -q tests/test_ci_workflow.py`
Expected: FAIL because the job is absent.

- [ ] **Step 3: Add CI job**

Add a Python 3.11 Ubuntu job that installs the package core-only and with `.[gemini]`, then imports scripted and Gemini adapters respectively.

- [ ] **Step 4: Verify green**

Run: `uv run python -m pytest -q tests/test_ci_workflow.py`
Expected: PASS.

### Task 4: Conductor Local Command Helper Extraction

**Files:**
- Create: `agy_swarms/conductor_commands.py`
- Modify: `agy_swarms/conductor.py`
- Test: `tests/test_conductor_test_node.py`

- [ ] **Step 1: Write failing import test**

```python
def test_conductor_command_helpers_are_importable():
    from agy_swarms.conductor_commands import command_error_envelope
```

- [ ] **Step 2: Verify red**

Run: `uv run python -m pytest -q tests/test_conductor_test_node.py::test_conductor_command_helpers_are_importable`
Expected: FAIL because the helper module does not exist.

- [ ] **Step 3: Move helper logic**

Move local command envelope construction helpers out of `Conductor` while preserving command-node behavior.

- [ ] **Step 4: Verify green**

Run: `uv run python -m pytest -q tests/test_conductor_test_node.py tests/test_local_runner_cli.py`
Expected: PASS.

### Final Verification

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run python -m pytest -q`
- [ ] `uv build`
- [ ] `uv run python scripts/release_health.py`
