# PR Verification Evidence Updater Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repeatable local command that refreshes PR verification evidence after each pushed commit.

**Architecture:** Keep GitHub Actions manual-only, matching the current billing policy. Add a small script that can render and replace a marked `## Verification` section in a PR body, with pure functions covered by tests and a CLI that shells out to `gh pr view/edit`.

**Tech Stack:** Python 3.11, argparse, subprocess, pytest, GitHub CLI.

---

### Task 1: Pin Body Update Behavior With Tests

**Files:**
- Create: `tests/test_pr_verification.py`

- [x] **Step 1: Add tests for rendering and idempotent replacement**

Cover:

```text
- rendered evidence includes commit, command, mypy file count, pytest count, and release-health probe count
- existing marked verification section is replaced
- bodies without markers get a new verification section appended
- legacy Test Plan evidence is replaced with the marked Verification section
```

- [x] **Step 2: Run the focused test**

Run:

```bash
uv run python -m pytest tests/test_pr_verification.py -q
```

Expected: fail until the script exists.

### Task 2: Implement The Script

**Files:**
- Create: `scripts/pr_verification.py`

- [x] **Step 1: Add pure formatting/update helpers**

Implement `render_verification_block(...)` and `update_body(...)` with stable markers:

```text
<!-- agy-verification:start -->
...
<!-- agy-verification:end -->
```

- [x] **Step 2: Add CLI wrapper around gh**

Support:

```bash
uv run python scripts/pr_verification.py --pr 2 --pytest-count 709 --mypy-files 95 --release-health-passed 24 --release-health-total 24
```

The CLI should read the current body with `gh pr view`, update it, and write it with `gh pr edit --body-file`.

### Task 3: Add A Make Target

**Files:**
- Modify: `Makefile`
- Modify: `tests/test_quality_command_contracts.py`

- [x] **Step 1: Add `pr-verification` target**

Add a Make target that runs the updater with environment defaults:

```make
pr-verification:
	uv run python scripts/pr_verification.py --pr "$${PR_NUMBER:?set PR_NUMBER}" --pytest-count "$${PYTEST_COUNT:-709}" --mypy-files "$${MYPY_FILES:-95}" --release-health-passed "$${RELEASE_HEALTH_PASSED:-24}" --release-health-total "$${RELEASE_HEALTH_TOTAL:-24}"
```

### Task 4: Verify, Commit, Push, And Refresh PR #2

**Files:**
- Read: project source and tests

- [x] **Step 1: Run focused tests**

Run:

```bash
uv run python -m pytest tests/test_pr_verification.py tests/test_quality_command_contracts.py -q
```

- [x] **Step 2: Run full verification**

Run:

```bash
make verify
```

- [ ] **Step 3: Commit and push**

Run:

```bash
git add Makefile scripts/pr_verification.py tests/test_pr_verification.py tests/test_quality_command_contracts.py docs/superpowers/plans/2026-06-09-pr-verification-evidence-updater.md
git commit -m "chore: add pr verification evidence updater"
git push
```

- [ ] **Step 4: Refresh PR #2 body**

Run:

```bash
uv run python scripts/pr_verification.py --pr 2 --pytest-count 709 --mypy-files 95 --release-health-passed 24 --release-health-total 24
```

Expected: PR #2 body shows current verification evidence for the pushed commit.
