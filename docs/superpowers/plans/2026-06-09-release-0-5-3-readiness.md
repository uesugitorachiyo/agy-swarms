# Release 0.5.3 Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare the merged repo-hardening and automatic-CI work as package release `0.5.3`.

**Architecture:** Treat this as a patch release: update package metadata and lockfile version, move relevant changelog bullets into a dated `v0.5.3` section, refresh versioning/release docs, and protect the release decision with contract tests.

**Tech Stack:** Python packaging metadata, uv lockfile, pytest contract tests, Markdown docs.

---

### Task 1: Release Policy Tests

**Files:**
- Modify: `tests/test_release_version_policy.py`

- [ ] **Step 1: Write failing tests**

Update release policy tests to expect:
- `pyproject.toml` version `0.5.3`
- `uv.lock` package entry for `agy-swarms` version `0.5.3`
- `CHANGELOG.md` section `## v0.5.3 - 2026-06-09`
- release notes for disk preflight, automatic CI triggers, PR verification updater cleanup, and verification counts
- `docs/versioning.md` records `v0.5.3` and automatic CI as release authority

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run python -m pytest tests/test_release_version_policy.py -q`

Expected: tests fail because metadata and docs still describe `0.5.2`.

### Task 2: Metadata and Docs Update

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `CHANGELOG.md`
- Modify: `docs/versioning.md`
- Modify: `README.md`

- [ ] **Step 1: Bump package metadata**

Set `pyproject.toml` and the `agy-swarms` package entry in `uv.lock` to `0.5.3`.

- [ ] **Step 2: Update release notes**

Move current hardening work into:

```markdown
## v0.5.3 - 2026-06-09
```

Document:
- verification disk preflight
- automatic PR and `main` push CI
- PR verification body updater cleanup
- full local and remote verification gates

- [ ] **Step 3: Update versioning and README**

Document `0.5.3` as the current package release and remove stale manual-only CI language from current policy. Keep old manual-only language only in historical changelog sections.

### Task 3: Verification and Landing

**Files:**
- Modify: all files above

- [ ] **Step 1: Run focused tests**

Run: `uv run python -m pytest tests/test_release_version_policy.py tests/test_quality_command_contracts.py -q`

Expected: focused release/docs tests pass.

- [ ] **Step 2: Run full verification**

Run: `make verify`

Expected: disk preflight, lint, format, mypy, docs drift, pytest, build, and release health pass.

- [ ] **Step 3: Open PR and wait for remote CI**

Push the branch, create a PR, refresh its verification block, wait for automatic PR CI, merge when clean, then verify the automatic `main` push CI starts and passes.

- [ ] **Step 4: Tag release if main is clean**

If local and remote main are clean after merge, create and push `v0.5.3`.
