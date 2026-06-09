# PR2 Merge Checklist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a concise, repeatable merge checklist for landing PR #2.

**Architecture:** Keep the checklist as documentation, not automation. It should capture the exact local verification, PR evidence refresh, remote CI review, merge strategy, and post-merge synchronization steps for this branch.

**Tech Stack:** Markdown, pytest contract tests, Make verification facade.

---

### Task 1: Pin Checklist Requirements

**Files:**
- Modify: `tests/test_quality_command_contracts.py`

- [x] **Step 1: Add failing doc contract**

Assert that `docs/pr2-merge-checklist.md` exists and mentions:

```text
- PR #2
- make verify
- make pr-verification PR_NUMBER=2
- remote CI/status checks
- merge strategy
- post-merge local sync
- no release tag/version bump unless explicitly chosen
```

- [x] **Step 2: Run the focused contract**

Run:

```bash
uv run python -m pytest tests/test_quality_command_contracts.py::test_pr2_merge_checklist_documents_landing_steps -q
```

Expected: fail until the doc exists.

### Task 2: Add The Checklist

**Files:**
- Create: `docs/pr2-merge-checklist.md`

- [x] **Step 1: Write the checklist**

Include pre-merge, merge, and post-merge steps with concrete commands.

### Task 3: Verify And Publish

**Files:**
- Read: project source and tests

- [x] **Step 1: Run focused tests**

Run:

```bash
uv run python -m pytest tests/test_quality_command_contracts.py -q
```

- [x] **Step 2: Run full verification**

Run:

```bash
make verify
```

- [ ] **Step 3: Commit, push, refresh evidence**

Run:

```bash
git add docs/pr2-merge-checklist.md tests/test_quality_command_contracts.py docs/superpowers/plans/2026-06-09-pr2-merge-checklist.md
git commit -m "docs: add pr2 merge checklist"
git push
make pr-verification PR_NUMBER=2
```

Expected: PR #2 includes the checklist and current verification evidence.
