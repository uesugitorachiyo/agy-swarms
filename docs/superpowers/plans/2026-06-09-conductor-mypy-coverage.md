# Conductor Mypy Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `agy_swarms/conductor.py` to the Makefile mypy target and fix the resulting type error.

**Architecture:** Keep the existing scoped mypy facade. Add the conductor file to the explicit file list and narrow `self.fallback_adapter` to a local non-optional variable before it is captured by the fallback execution lambda.

**Tech Stack:** Python typing, mypy `--explicit-package-bases`, pytest contract test, Ruff.

---

### Task 1: Add Type-Check Coverage Contract

**Files:**
- Modify: `tests/test_quality_command_contracts.py`

- [ ] **Step 1: Write the failing test assertion**

Add `"agy_swarms/conductor.py"` to the list asserted by `test_makefile_typecheck_covers_cli_runner_and_release_health_modules`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/test_quality_command_contracts.py::test_makefile_typecheck_covers_cli_runner_and_release_health_modules`
Expected: FAIL because the Makefile does not list `agy_swarms/conductor.py`.

### Task 2: Fix Conductor Type Gap

**Files:**
- Modify: `agy_swarms/conductor.py`

- [ ] **Step 1: Narrow fallback adapter**

After `if self.fallback_adapter is None: return None`, assign `fallback_adapter = self.fallback_adapter` and use that local variable for capability checks, accounting, event naming, and fallback dispatch.

- [ ] **Step 2: Add conductor to Makefile type-check**

Add `agy_swarms/conductor.py` to the `type-check` target.

- [ ] **Step 3: Run focused type-check**

Run: `make type-check`
Expected: PASS.

### Task 3: Focused Tests

**Files:**
- No additional edits.

- [ ] **Step 1: Run fallback/conductor tests**

Run: `uv run python -m pytest -q tests/test_conductor.py tests/test_conductor_fallback.py tests/test_hybrid_review.py`
Expected: PASS.

### Task 4: Full Verification

**Files:**
- No code edits.

- [ ] **Step 1: Run verification commands**

Run:
- `uv run ruff check .`
- `uv run ruff format --check .`
- `make type-check`
- `uv run python -m pytest -q`
- `uv build`
- `uv run python scripts/release_health.py`

Expected: all commands exit 0.
