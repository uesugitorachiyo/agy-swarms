# Automatic CI Triggers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-enable automatic GitHub Actions verification for pull requests and pushes to `main`.

**Architecture:** Keep the existing split between fast matrix checks, package install smoke checks, and release-health. Change only the workflow event policy and operator docs, then protect the new trigger policy with text-level contract tests.

**Tech Stack:** GitHub Actions YAML, pytest contract tests, Markdown docs.

---

### Task 1: Trigger Policy Contracts

**Files:**
- Modify: `tests/test_ci_workflow.py`
- Modify: `tests/test_quality_command_contracts.py`

- [ ] **Step 1: Write failing tests**

Add assertions that `.github/workflows/ci.yml` contains:

```yaml
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
  workflow_dispatch:
```

Also assert docs no longer describe GitHub Actions as manual-only while billing is postponed.

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run python -m pytest tests/test_ci_workflow.py tests/test_quality_command_contracts.py::test_release_docs_document_automatic_ci_triggers -q`

Expected: failures because the workflow is still manual-only and docs still say manual-only.

### Task 2: Workflow and Docs Update

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/release-verification.md`
- Modify: `docs/architecture.md`

- [ ] **Step 1: Update workflow**

Replace the manual-only trigger with automatic PR and main-push triggers while keeping `workflow_dispatch`:

```yaml
on:
  pull_request:
    branches:
      - main
  push:
    branches:
      - main
  workflow_dispatch:
```

- [ ] **Step 2: Update docs**

Describe CI as automatic for pull requests and pushes to `main`, with `workflow_dispatch` reserved for manual reruns.

- [ ] **Step 3: Run focused tests**

Run: `uv run python -m pytest tests/test_ci_workflow.py tests/test_quality_command_contracts.py -q`

Expected: focused tests pass.

### Task 3: Verification and PR

**Files:**
- Modify: all files above

- [ ] **Step 1: Run full verification**

Run: `make verify`

Expected: disk preflight, lint, format, mypy, docs drift, pytest, build, and release health pass.

- [ ] **Step 2: Commit and push**

```bash
git add .github/workflows/ci.yml docs/architecture.md docs/release-verification.md docs/superpowers/plans/2026-06-09-automatic-ci-triggers.md tests/test_ci_workflow.py tests/test_quality_command_contracts.py
git commit -m "ci: enable automatic pr and main checks"
git push -u origin codex/automatic-ci-triggers
```

- [ ] **Step 3: Create PR and inspect remote checks**

Create a PR against `main`, refresh the PR verification block with `make pr-verification`, and inspect `gh run list --branch codex/automatic-ci-triggers --limit 10` to confirm whether remote Actions started.
