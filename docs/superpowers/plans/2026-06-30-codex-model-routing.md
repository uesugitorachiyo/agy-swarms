# Codex Model Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route planner, reviewer/evaluator, and closer roles to `gpt-5.5` with high reasoning, while routine roles default to `gpt-5.3-codex-spark`.

**Architecture:** Add one shared Codex model profile helper, then consume it from review routing, Codex CLI command construction, and the general model router. Keep environment overrides so unavailable model access can be corrected without another code change.

**Tech Stack:** Python, pytest, Codex CLI model flags.

## Global Constraints

- Preserve read-only Codex CLI execution for reviewer and closer nodes.
- Keep role-specific environment overrides.
- Do not reintroduce Antigravity subscription assumptions.
- Keep the archived repo change narrow.

---

### Task 1: Shared Codex Model Profiles

**Files:**
- Create: `agy_swarms/codex_models.py`
- Modify: `tests/test_codex_adapter.py`
- Modify: `tests/test_hybrid_review.py`
- Modify: `tests/test_model_routing.py`

**Interfaces:**
- Produces: `resolve_codex_role_model(role: str, env: Mapping[str, str] | None = None, light_effort: str | None = None) -> CodexRoleModel`
- Produces: `CodexRoleModel(model: str, reasoning_effort: str, profile: str)`

- [ ] **Step 1: Write failing tests**
- [ ] **Step 2: Verify the tests fail because the helper and new routing do not exist**
- [ ] **Step 3: Implement the shared helper and wire it into existing routing**
- [ ] **Step 4: Run focused tests**
- [ ] **Step 5: Run broader model/review tests**
