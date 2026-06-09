# Review Budget Events Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract review budget alert and closer auto-triage event construction out of `agy_swarms/conductor.py`.

**Architecture:** Add a focused `agy_swarms/conductor_review_budget.py` helper that receives primitive values and returns the emitted events plus the resulting closer adapter. Keep `Conductor` responsible only for deciding when to call it and appending returned events to its event log.

**Tech Stack:** Python helper module, pytest red-green tests, Ruff, mypy, existing conductor event contracts.

---

### Task 1: Add Review Budget Helper Contract

**Files:**
- Modify: `tests/test_conductor.py`

- [ ] **Step 1: Write the failing test**

Add a test importing `review_budget_events` from `agy_swarms.conductor_review_budget`. Assert that a worker emits no events, a closer over 1000 tokens emits only a `review_budget_alert`, and a reviewer over 1000 tokens with closer `agy` emits a `review_budget_alert` and `review_auto_triage` while returning closer `codex`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_review_budget_helper_is_importable`
Expected: FAIL with `ModuleNotFoundError` or missing import.

### Task 2: Implement Review Budget Helper

**Files:**
- Create: `agy_swarms/conductor_review_budget.py`

- [ ] **Step 1: Add pure helper**

Implement `review_budget_events(node_id: str, role: str, spent_tokens: int, closer: str, threshold: int = 1000) -> tuple[list[dict[str, object]], str]`.

- [ ] **Step 2: Run helper test to verify it passes**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_review_budget_helper_is_importable`
Expected: PASS.

### Task 3: Wire Conductor Through Helper

**Files:**
- Modify: `agy_swarms/conductor.py`

- [ ] **Step 1: Replace duplicated event blocks**

Import `review_budget_events`. Change `_maybe_record_review_budget_alert` to extend `self.events` and update `self.closer` from helper output. Replace the three inline review-budget event blocks in dispatch/fallback code with calls to `_maybe_record_review_budget_alert`.

- [ ] **Step 2: Run focused behavior tests**

Run: `uv run python -m pytest -q tests/test_conductor.py tests/test_hybrid_review.py tests/test_conductor_fallback.py`
Expected: PASS.

### Task 4: Add Type-Check Coverage

**Files:**
- Modify: `Makefile`
- Modify: `tests/test_quality_command_contracts.py`

- [ ] **Step 1: Write failing coverage assertion**

Assert `agy_swarms/conductor_review_budget.py` appears in the Makefile `type-check` target.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/test_quality_command_contracts.py::test_makefile_typecheck_covers_cli_runner_and_release_health_modules`
Expected: FAIL until the Makefile target includes the helper.

- [ ] **Step 3: Add helper to Makefile type-check**

Append `agy_swarms/conductor_review_budget.py` to the `type-check` target.

- [ ] **Step 4: Run `make type-check`**

Expected: PASS.

### Task 5: Full Verification

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
