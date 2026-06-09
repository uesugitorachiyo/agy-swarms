# Full Package Mypy Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the curated mypy target list with full-package coverage while keeping release scripts covered.

**Architecture:** First run the broader mypy command to expose the real type surface, then fix the reported type mismatches without changing runtime behavior. Finally, update the Makefile and contract tests so future verification keeps full-package coverage.

**Tech Stack:** Python 3.11, mypy, Ruff, pytest, uv, Makefile.

---

### Task 1: Capture The Full-Package Mypy Baseline

**Files:**
- Read: `Makefile`
- Read: `pyproject.toml`

- [x] **Step 1: Run full-package mypy**

Run:

```bash
uv run mypy --explicit-package-bases agy_swarms scripts/release_health.py scripts/release_health_registry.py scripts/release_health_docs.py scripts/rewrite_release_health_docs.py
```

Expected: Fail before implementation, proving the current target list does not cover all package modules.

Observed: 8 errors across `agy_swarms/eval/report.py`, `agy_swarms/gates.py`, `agy_swarms/reducers.py`, `agy_swarms/graph_io.py`, and `agy_swarms/phase2_exit.py`.

### Task 2: Fix The Reported Type Errors

**Files:**
- Modify: `agy_swarms/eval/report.py`
- Modify: `agy_swarms/gates.py`
- Modify: `agy_swarms/reducers.py`
- Modify: `agy_swarms/graph_io.py`
- Modify: `agy_swarms/phase2_exit.py`

- [x] **Step 1: Make tuple/list and optional-value types explicit**

Apply narrow edits:

```text
- annotate the Phase 5 gate tuple as variadic
- avoid assigning a narrowed fake socket callable to the typed stdlib attribute without a cast
- validate reducer.custom_id before registry indexing
- construct TaskGraph with lists where the dataclass expects lists
- type Phase 2 subtask dictionaries as string values instead of inferred string sequences
```

- [x] **Step 2: Re-run full-package mypy**

Run:

```bash
uv run mypy --explicit-package-bases agy_swarms scripts/release_health.py scripts/release_health_registry.py scripts/release_health_docs.py scripts/rewrite_release_health_docs.py
```

Expected: Success over all package modules and covered release scripts.

### Task 3: Promote Full-Package Coverage Into Verification

**Files:**
- Modify: `Makefile`
- Modify: `tests/test_quality_command_contracts.py`

- [x] **Step 1: Replace the explicit module list**

Update `type-check` to run:

```bash
uv run mypy --explicit-package-bases agy_swarms scripts/release_health.py scripts/release_health_registry.py scripts/release_health_docs.py scripts/rewrite_release_health_docs.py
```

- [x] **Step 2: Update contract tests**

Assert that `Makefile` type-checks `agy_swarms` as a package and still includes the release-health script modules.

### Task 4: Verify And Publish

**Files:**
- Read: project source and tests

- [x] **Step 1: Run the full verification facade**

Run:

```bash
make verify
```

Expected: Ruff, format check, full-package mypy, docs drift, pytest, build, and release health all pass.

- [ ] **Step 2: Commit and push the PR branch**

Run:

```bash
git add Makefile docs/superpowers/plans/2026-06-09-full-package-mypy.md tests/test_quality_command_contracts.py agy_swarms/eval/report.py agy_swarms/gates.py agy_swarms/reducers.py agy_swarms/graph_io.py agy_swarms/phase2_exit.py
git commit -m "chore: expand mypy to full package"
git push
```

Expected: PR #2 updates with one focused follow-up commit.
