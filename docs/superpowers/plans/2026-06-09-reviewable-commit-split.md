# Reviewable Commit Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the accumulated repository improvements into a reviewable sequence of commits with fresh verification afterward.

**Architecture:** Keep the split aligned to ownership boundaries that reviewers can reason about: release and dependency hardening, CLI command modularization, and conductor/test/docs modularization. Do not rewrite the implementation while splitting; only stage and commit the already-verified work.

**Tech Stack:** Git, uv, Ruff, mypy, pytest, release-health scripts.

---

### Task 1: Inspect And Group The Worktree

**Files:**
- Read: `git status --short`
- Read: `git log --oneline -5`

- [x] **Step 1: Confirm the branch and dirty files**

Run:

```bash
git status --short
git branch --show-current
git log --oneline -5
```

Expected: current branch is `main`, with the improvement files dirty and no unrelated blocking changes detected.

- [x] **Step 2: Confirm commit identity**

Run:

```bash
git config user.name
git config user.email
```

Expected: both commands print configured values.

### Task 2: Commit Release, Dependency, And Verification Hardening

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.pre-commit-config.yaml`
- Modify: `agy_swarms/adapters/__init__.py`
- Modify: `agy_swarms/adapters/codex.py`
- Modify: `agy_swarms/review_escalation.py`
- Modify: `agy_swarms/review_telemetry.py`
- Modify: `docs/release-verification.md`
- Modify: `pyproject.toml`
- Modify: `scripts/release_health.py`
- Create: `scripts/release_health_docs.py`
- Create: `scripts/release_health_registry.py`
- Create: `scripts/rewrite_release_health_docs.py`
- Modify: `tests/test_adapter_imports.py`
- Modify: `tests/test_ci_workflow.py`
- Modify: `tests/test_codex_adapter.py`
- Modify: `tests/test_package_extras_smoke.py`
- Modify: `tests/test_release_health.py`
- Modify: `tests/test_review_benchmark.py`
- Modify: `uv.lock`

- [x] **Step 1: Stage the verification hardening files**

Run:

```bash
git add .github/workflows/ci.yml .pre-commit-config.yaml agy_swarms/adapters/__init__.py agy_swarms/adapters/codex.py agy_swarms/review_escalation.py agy_swarms/review_telemetry.py docs/release-verification.md pyproject.toml scripts/release_health.py scripts/release_health_docs.py scripts/release_health_registry.py scripts/rewrite_release_health_docs.py tests/test_adapter_imports.py tests/test_ci_workflow.py tests/test_codex_adapter.py tests/test_package_extras_smoke.py tests/test_release_health.py tests/test_review_benchmark.py uv.lock
```

- [x] **Step 2: Commit the staged changes**

Run:

```bash
git commit -m "chore: harden release verification"
```

Expected: one commit containing release-health, CI, dependency, and adapter import hardening.

### Task 3: Commit CLI Command Modularization

**Files:**
- Create: `agy_swarms/cli.py`
- Create: `agy_swarms/commands/`
- Modify: `agy_swarms/main.py`
- Modify: `tests/test_cli.py`

- [x] **Step 1: Stage CLI files**

Run:

```bash
git add agy_swarms/cli.py agy_swarms/commands agy_swarms/main.py tests/test_cli.py
```

- [x] **Step 2: Commit the staged changes**

Run:

```bash
git commit -m "refactor: split cli command handlers"
```

Expected: one commit focused on command dispatch boundaries.

### Task 4: Commit Conductor Modularization And Documentation

**Files:**
- Create: `Makefile`
- Modify: `README.md`
- Modify: `agy_swarms/conductor.py`
- Create: `agy_swarms/conductor_adapters.py`
- Create: `agy_swarms/conductor_budget.py`
- Create: `agy_swarms/conductor_checkpointing.py`
- Create: `agy_swarms/conductor_commands.py`
- Create: `agy_swarms/conductor_drift.py`
- Create: `agy_swarms/conductor_fallback.py`
- Create: `agy_swarms/conductor_pipeline.py`
- Create: `agy_swarms/conductor_reports.py`
- Create: `agy_swarms/conductor_review.py`
- Create: `agy_swarms/conductor_review_budget.py`
- Create: `docs/architecture.md`
- Create: `docs/superpowers/plans/`
- Modify: `tests/test_conductor_test_node.py`
- Create: `tests/test_conductor_helpers.py`
- Create: `tests/test_quality_command_contracts.py`

- [x] **Step 1: Stage conductor, docs, and quality files**

Run:

```bash
git add Makefile README.md agy_swarms/conductor.py agy_swarms/conductor_*.py docs/architecture.md docs/superpowers/plans tests/test_conductor_test_node.py tests/test_conductor_helpers.py tests/test_quality_command_contracts.py
```

- [x] **Step 2: Commit the staged changes**

Run:

```bash
git commit -m "refactor: split conductor helpers"
```

Expected: one commit focused on conductor module boundaries, architecture documentation, and command contracts.

### Task 5: Verify The Committed Change Set

**Files:**
- Read: `Makefile`
- Read: project source and tests

- [x] **Step 1: Run the full verification facade**

Run:

```bash
make verify
```

Expected: Ruff check passes, Ruff format check passes, mypy passes, release-verification docs are current, pytest passes, build succeeds, and release health passes.

- [ ] **Step 2: Confirm final git state**

Run:

```bash
git status --short
```

Expected: no dirty tracked or untracked files from this work.
