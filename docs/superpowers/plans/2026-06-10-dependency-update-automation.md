# Dependency Update Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tested Dependabot update automation for GitHub Actions and Python dependency manifests.

**Architecture:** Add `.github/dependabot.yml` with two weekly update groups: `github-actions` for workflow actions and `uv` for `pyproject.toml`/`uv.lock` at the repository root. Keep the policy narrow with conservative open PR limits, labels, and grouped update names. Add tests that parse the config text and docs that explain the cadence and expected review path.

**Tech Stack:** GitHub Dependabot configuration, pytest contract tests, Markdown docs.

---

### Task 1: Pin Dependabot Policy

**Files:**
- Modify: `tests/test_ci_workflow.py`

- [x] **Step 1: Write failing policy tests**

Add tests that require `.github/dependabot.yml` to exist and contain:
- `version: 2`
- one `package-ecosystem: "github-actions"` update for `/`
- one `package-ecosystem: "uv"` update for `/`
- weekly schedules
- `open-pull-requests-limit: 5`
- labels `dependencies` and `ci`
- groups named `github-actions` and `python-dependencies`

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run python -m pytest tests/test_ci_workflow.py::test_dependabot_config_updates_github_actions_and_uv_dependencies tests/test_ci_workflow.py::test_dependabot_docs_explain_update_policy -q
```

Expected: fail because `.github/dependabot.yml` and docs references do not exist.

### Task 2: Add Dependabot Config And Docs

**Files:**
- Create: `.github/dependabot.yml`
- Create: `docs/dependency-updates.md`
- Modify: `README.md`

- [x] **Step 1: Add `.github/dependabot.yml`**

Configure weekly updates for GitHub Actions and uv dependencies in `/`, with grouped update names and conservative PR limits.

- [x] **Step 2: Document the policy**

Add `docs/dependency-updates.md` explaining the weekly cadence, update groups, and requirement to let CI pass before merging. Link it from `README.md`.

- [x] **Step 3: Run focused tests**

Run:

```bash
uv run python -m pytest tests/test_ci_workflow.py::test_dependabot_config_updates_github_actions_and_uv_dependencies tests/test_ci_workflow.py::test_dependabot_docs_explain_update_policy -q
```

Expected: both tests pass.

### Task 3: Verify

**Files:**
- No additional edits expected.

- [x] **Step 1: Run full verification**

Run:

```bash
make verify
```

Expected: lint, format, mypy, docs drift, pytest, build, and release health pass.
