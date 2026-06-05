# Codex Hybrid Review Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve Codex hybrid reviewer/closer accuracy while controlling cost and keeping orchestration deterministic.

**Architecture:** Keep `agy-swarms` as the deterministic graph runtime and add smarter Codex review behavior behind the existing adapter boundary. Codex remains read-only; it receives role-specific schemas, evidence bundles, tiered model settings, batched node review support, disagreement escalation policy, and telemetry records.

**Tech Stack:** Python 3.13, pytest, ruff, Codex CLI subprocess adapter, JSON schemas, dataclasses.

---

### Task 1: Role-Specific Codex Schemas And Prompts

**Files:**
- Modify: `agy_swarms/adapters/codex.py`
- Test: `tests/test_codex_adapter.py`

- [ ] **Step 1: Write failing tests**

Add tests asserting reviewer output contains file-scoped findings and closer output contains evidence-bound acceptance fields.

- [ ] **Step 2: Run failing tests**

Run: `uv run python -m pytest -q tests/test_codex_adapter.py`
Expected: FAIL because current schema is generic.

- [ ] **Step 3: Implement role-specific schema selection and prompts**

Add `_schema_for_role(role)`, `_review_prompt(node)`, and parsing helpers that preserve existing `artifact["route"]`, `artifact["review"]`, `concerns`, and `blockers`.

- [ ] **Step 4: Verify green**

Run: `uv run python -m pytest -q tests/test_codex_adapter.py`
Expected: PASS.

### Task 2: Codex Tier Configuration

**Files:**
- Modify: `agy_swarms/adapters/codex.py`
- Test: `tests/test_codex_adapter.py`

- [ ] **Step 1: Write failing tests**

Add tests for default `gpt-5.5`/`low`, closer high-effort override, and environment variable override.

- [ ] **Step 2: Run failing tests**

Run: `uv run python -m pytest -q tests/test_codex_adapter.py`
Expected: FAIL until settings are resolved from role-aware config.

- [ ] **Step 3: Implement `CodexModelConfig`**

Add a small dataclass and `resolve_codex_model_config(role, escalated=False, env=os.environ)` that separates model slug from reasoning effort.

- [ ] **Step 4: Verify green**

Run: `uv run python -m pytest -q tests/test_codex_adapter.py`
Expected: PASS.

### Task 3: Batched Codex Subgraph Review

**Files:**
- Modify: `agy_swarms/adapters/codex.py`
- Test: `tests/test_codex_adapter.py`

- [ ] **Step 1: Write failing tests**

Add a test for `CodexAdapter.run_batch(nodes)` that sends one Codex command and returns one `ResultEnvelope` per node from a `nodes` JSON object.

- [ ] **Step 2: Run failing tests**

Run: `uv run python -m pytest -q tests/test_codex_adapter.py::test_codex_adapter_batches_review_nodes_in_one_exec`
Expected: FAIL because `run_batch` does not exist.

- [ ] **Step 3: Implement minimal batching**

Add a batch schema, batch prompt, and parser. Do not change conductor scheduling yet; expose the primitive for future subgraph-level conductor integration.

- [ ] **Step 4: Verify green**

Run: `uv run python -m pytest -q tests/test_codex_adapter.py`
Expected: PASS.

### Task 4: Disagreement Escalation Policy

**Files:**
- Create: `agy_swarms/review_escalation.py`
- Test: `tests/test_review_escalation.py`

- [ ] **Step 1: Write failing tests**

Add tests for `agy pass + codex block`, `reviewer concerns + closer pass`, and no-escalation agreement cases.

- [ ] **Step 2: Run failing tests**

Run: `uv run python -m pytest -q tests/test_review_escalation.py`
Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement policy**

Add `ReviewVerdict`, `EscalationDecision`, and `decide_review_escalation(primary, secondary)` with deterministic reasons.

- [ ] **Step 4: Verify green**

Run: `uv run python -m pytest -q tests/test_review_escalation.py`
Expected: PASS.

### Task 5: Reviewer Telemetry Ledger

**Files:**
- Create: `agy_swarms/review_telemetry.py`
- Test: `tests/test_review_telemetry.py`

- [ ] **Step 1: Write failing tests**

Add tests that append JSONL telemetry without code contents and aggregate precision-style counters from later outcomes.

- [ ] **Step 2: Run failing tests**

Run: `uv run python -m pytest -q tests/test_review_telemetry.py`
Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement telemetry helpers**

Add `ReviewTelemetryRecord`, `append_review_telemetry(path, record)`, and `summarize_review_telemetry(path)`.

- [ ] **Step 4: Verify green**

Run: `uv run python -m pytest -q tests/test_review_telemetry.py`
Expected: PASS.

### Task 6: Full Verification

**Files:**
- All modified files.

- [ ] **Step 1: Run lint**

Run: `uv run ruff check .`
Expected: PASS.

- [ ] **Step 2: Run full tests**

Run: `uv run python -m pytest -q`
Expected: PASS.

- [ ] **Step 3: Run live smoke**

Run a tiny `CodexAdapter().run(NodeSpec(...))` smoke manually.
Expected: structured JSON envelope with `status=succeeded`, `model=gpt-5.5`, and `thinking_level=low`.
