# Cross-Platform Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make macOS and Windows verification first-class without automatically spending GitHub Actions minutes.

**Architecture:** Keep GitHub Actions manual-only while expanding the existing workflow to a matrix across Ubuntu, macOS, and Windows. Add tests that inspect the workflow contract and documentation so cross-platform verification cannot silently regress.

**Tech Stack:** GitHub Actions YAML, Python `pytest`, `uv`, Ruff, Hatchling build via `uv build`.

---

### Task 1: Lock CI Matrix Contract

**Files:**
- Create: `tests/test_ci_workflow.py`
- Modify: `.github/workflows/ci.yml`

- [x] **Step 1: Write failing tests**

Add tests that require `workflow_dispatch`, forbid automatic `push`/`pull_request` triggers, require `ubuntu-latest`, `macos-latest`, and `windows-latest`, and require `uv build`.

- [x] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_ci_workflow.py -q`

Expected before YAML update: failure because the workflow only targets Ubuntu and has automatic triggers.

- [x] **Step 3: Update workflow**

Change `.github/workflows/ci.yml` to a manual matrix job with OS names, `PYTHONIOENCODING=utf-8`, Ruff, pytest, and build.

- [x] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_ci_workflow.py -q`

Expected after YAML update: pass.

### Task 2: Document Operator Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/release-verification.md`
- Test: `tests/test_release_version_policy.py`

- [x] **Step 1: Write/update tests**

Extend existing release/version documentation assertions to require cross-platform CI and `uv build` references.

- [x] **Step 2: Run focused tests**

Run: `uv run python -m pytest tests/test_release_version_policy.py tests/test_ci_workflow.py -q`

- [x] **Step 3: Update docs**

Document local macOS/Windows commands and manual GitHub Actions matrix verification.

- [x] **Step 4: Run full verification**

Run: `uv run ruff check .`, `uv run python -m pytest -q`, and `uv build --out-dir <temp>`.
