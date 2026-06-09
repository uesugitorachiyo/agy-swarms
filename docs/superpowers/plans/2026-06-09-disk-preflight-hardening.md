# Disk Preflight Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent expensive verification runs from failing late because the workspace or temp volume is nearly full.

**Architecture:** Add a small Python preflight script that checks free bytes on the repository root and temp directory before heavy Make targets run. Wire the script into `verify-fast`, `verify`, and `release-health`, and document the default threshold plus `TMPDIR` override guidance.

**Tech Stack:** Python standard library, Make, pytest, Markdown docs.

---

### Task 1: Disk Preflight Script

**Files:**
- Create: `scripts/disk_space_preflight.py`
- Test: `tests/test_disk_space_preflight.py`

- [ ] **Step 1: Write failing tests**

Add tests that verify:
- paths below the required threshold return a failure result,
- duplicate filesystem paths are checked once,
- CLI output explains the required space and how to set `TMPDIR`,
- environment variable `AGY_VERIFY_MIN_FREE_MIB` overrides the default.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_disk_space_preflight.py -q`

Expected: import or behavior failure because `scripts.disk_space_preflight` does not exist yet.

- [ ] **Step 3: Implement the script**

Create `scripts/disk_space_preflight.py` with:
- `DEFAULT_MIN_FREE_MIB = 1024`
- `PreflightCheck` and `PreflightResult` dataclasses
- `collect_paths(repo_root: Path, temp_dir: Path) -> list[Path]`
- `run_preflight(paths: Iterable[Path], min_free_mib: int) -> PreflightResult`
- a CLI that accepts `--min-free-mib`, `--path`, and `--label`, and falls back to `AGY_VERIFY_MIN_FREE_MIB`.

- [ ] **Step 4: Run focused tests**

Run: `uv run python -m pytest tests/test_disk_space_preflight.py -q`

Expected: all disk preflight tests pass.

### Task 2: Makefile and Docs Contracts

**Files:**
- Modify: `Makefile`
- Modify: `docs/architecture.md`
- Modify: `docs/release-verification.md`
- Test: `tests/test_quality_command_contracts.py`

- [ ] **Step 1: Write failing contract tests**

Add assertions that:
- `Makefile` exposes `disk-preflight`,
- `verify-fast` depends on `disk-preflight`,
- `release-health` depends on `disk-preflight`,
- docs mention `AGY_VERIFY_MIN_FREE_MIB`, `TMPDIR`, and at least `1 GiB` of free space.

- [ ] **Step 2: Run contract tests to verify they fail**

Run: `uv run python -m pytest tests/test_quality_command_contracts.py::test_makefile_runs_disk_preflight_before_heavy_verification tests/test_quality_command_contracts.py::test_release_docs_document_disk_preflight -q`

Expected: failures because the Makefile and docs have not been updated yet.

- [ ] **Step 3: Update Makefile and docs**

Add:

```make
disk-preflight:
	uv run python scripts/disk_space_preflight.py

release-health: disk-preflight
verify-fast: disk-preflight lint format-check type-check verify-docs test build
```

Document the default 1 GiB free-space requirement and the overrides:

```bash
AGY_VERIFY_MIN_FREE_MIB=2048 make verify
TMPDIR=/path/with/space make verify
```

- [ ] **Step 4: Run focused contracts**

Run: `uv run python -m pytest tests/test_quality_command_contracts.py tests/test_disk_space_preflight.py -q`

Expected: focused tests pass.

### Task 3: Full Verification and Commit

**Files:**
- Modify: all files changed above

- [ ] **Step 1: Run full verification**

Run: `make verify`

Expected: disk preflight passes first, then lint, format, mypy, docs drift, pytest, build, and release health pass.

- [ ] **Step 2: Commit**

```bash
git add Makefile docs/architecture.md docs/release-verification.md docs/superpowers/plans/2026-06-09-disk-preflight-hardening.md scripts/disk_space_preflight.py tests/test_disk_space_preflight.py tests/test_quality_command_contracts.py
git commit -m "chore: add verification disk preflight"
```

- [ ] **Step 3: Push and prepare review**

```bash
git push -u origin codex/disk-preflight-hardening
gh pr create --base main --head codex/disk-preflight-hardening --title "Add verification disk preflight" --body-file <generated-body>
```
