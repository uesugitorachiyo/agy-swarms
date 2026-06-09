# Command And Release Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Continue reducing large-file and release-doc drift risk after the first structure hardening pass.

**Architecture:** Move CLI command handlers behind `agy_swarms.commands`, keep `agy_swarms.main:main` as the console entrypoint, generate the release-health probe docs from `scripts.release_health_registry`, add install-extra smoke tests, and extract conductor helper functions without changing conductor behavior.

**Tech Stack:** Python 3.11+, uv, pytest, ruff, hatchling.

---

### Task 1: Command Handler Package

**Files:**
- Create: `agy_swarms/commands/__init__.py`
- Modify: `agy_swarms/cli.py`
- Modify: `agy_swarms/main.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing test**

```python
def test_cli_dispatch_uses_commands_package():
    import agy_swarms.commands as commands
    assert hasattr(commands, "cmd_run")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/test_cli.py::test_cli_dispatch_uses_commands_package`
Expected: FAIL with missing module.

- [ ] **Step 3: Move command handlers**

Move all `cmd_*`, CLI helper functions, and CLI-only imports from `agy_swarms/main.py` into `agy_swarms/commands/__init__.py`. Update `agy_swarms/cli.py` dispatch to import `agy_swarms.commands`.

- [ ] **Step 4: Verify**

Run: `uv run python -m pytest -q tests/test_cli.py`
Expected: PASS.

### Task 2: Release Docs From Registry

**Files:**
- Create: `scripts/release_health_docs.py`
- Modify: `docs/release-verification.md`
- Test: `tests/test_release_health.py`

- [ ] **Step 1: Write failing test**

```python
def test_release_docs_probe_list_matches_registry():
    from scripts.release_health_docs import render_probe_list
    assert render_probe_list() in Path("docs/release-verification.md").read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/test_release_health.py::test_release_docs_probe_list_matches_registry`
Expected: FAIL with missing module.

- [ ] **Step 3: Implement renderer**

Render every probe command from `PROBES` as markdown bullets. Replace the manual list in `docs/release-verification.md` with renderer output.

- [ ] **Step 4: Verify**

Run: `uv run python -m pytest -q tests/test_release_health.py`
Expected: PASS.

### Task 3: Extras Smoke Tests

**Files:**
- Create: `tests/test_package_extras_smoke.py`

- [ ] **Step 1: Write tests**

Use temporary venvs with `uv pip install .` and `uv pip install ".[gemini]"` to prove the core install imports scripted adapter without `google-genai` and the gemini extra imports `GeminiApiAdapter`.

- [ ] **Step 2: Run tests**

Run: `uv run python -m pytest -q tests/test_package_extras_smoke.py`
Expected: PASS.

### Task 4: Conductor Budget Helpers

**Files:**
- Create: `agy_swarms/conductor_budget.py`
- Modify: `agy_swarms/conductor.py`
- Test: `tests/test_conductor.py`

- [ ] **Step 1: Write failing test**

```python
def test_conductor_budget_helpers_are_importable():
    from agy_swarms.conductor_budget import billable_tokens
    assert billable_tokens({"output": 2, "thinking": 3}) == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_conductor_budget_helpers_are_importable`
Expected: FAIL with missing module.

- [ ] **Step 3: Move helpers**

Move `_dims`, `_billable`, and `_add_consumed` into `agy_swarms/conductor_budget.py` as public helper names, and import aliases in `conductor.py` to preserve local call sites.

- [ ] **Step 4: Verify**

Run: `uv run python -m pytest -q tests/test_conductor.py`
Expected: PASS.

### Final Verification

- [ ] Run `uv run ruff check .`
- [ ] Run `uv run ruff format --check .`
- [ ] Run `uv run python -m pytest -q`
- [ ] Run `uv build`
- [ ] Run `uv run python scripts/release_health.py`
