# Architecture Boundaries Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Document the command/conductor/helper boundaries introduced by the refactor.

**Architecture:** Add a single `docs/architecture.md` file that names the actual modules in the repository and explains ownership boundaries. Link it from `README.md` so release and onboarding docs point readers to the architecture map.

**Tech Stack:** Markdown documentation, pytest contract tests, existing local verification commands.

---

### Task 1: Add Documentation Contract Test

**Files:**
- Modify: `tests/test_quality_command_contracts.py`

- [ ] **Step 1: Write the failing test**

Add `test_architecture_doc_describes_command_conductor_and_helper_boundaries`. It should read `docs/architecture.md` and assert the file mentions `agy_swarms/cli.py`, `agy_swarms/commands/`, `agy_swarms/conductor.py`, `agy_swarms/conductor_budget.py`, `agy_swarms/conductor_checkpointing.py`, `agy_swarms/conductor_fallback.py`, `agy_swarms/conductor_pipeline.py`, `agy_swarms/conductor_drift.py`, `scripts/release_health.py`, and `scripts/release_health_registry.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/test_quality_command_contracts.py::test_architecture_doc_describes_command_conductor_and_helper_boundaries`
Expected: FAIL because `docs/architecture.md` does not exist.

### Task 2: Write Architecture Documentation

**Files:**
- Create: `docs/architecture.md`
- Modify: `README.md`

- [ ] **Step 1: Add `docs/architecture.md`**

Document:
- CLI entrypoint and command modules.
- Conductor orchestration responsibilities.
- Helper module boundaries.
- Release health registry/runner split.
- Type-check and verification facade.

- [ ] **Step 2: Link from README**

Add a short sentence in the release/docs area linking to `docs/architecture.md`.

- [ ] **Step 3: Run docs contract test**

Run: `uv run python -m pytest -q tests/test_quality_command_contracts.py::test_architecture_doc_describes_command_conductor_and_helper_boundaries`
Expected: PASS.

### Task 3: Full Verification

**Files:**
- No additional edits.

- [ ] **Step 1: Run verification commands**

Run:
- `uv run ruff check .`
- `uv run ruff format --check .`
- `make type-check`
- `uv run python -m pytest -q`
- `uv build`
- `uv run python scripts/release_health.py`

Expected: all commands exit 0.
