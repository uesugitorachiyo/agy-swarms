# Release 0.5.5 Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut package release `0.5.5` so the newly added GitHub Release asset verifier is published and exercised against real release assets.

**Architecture:** Treat this as a patch release from `main`: update package metadata, lockfile version, changelog, and versioning docs, then use the existing release operator checklist for PR, CI, tag, GitHub Release publishing, and asset verification. The release verifier should be exercised only after the tag workflow publishes `SHA256SUMS.txt`.

**Tech Stack:** Python packaging with `pyproject.toml`, `uv.lock`, GitHub Actions, GitHub CLI, Makefile verification.

---

### Task 1: Release Metadata

**Files:**
- Modify: `tests/test_release_version_policy.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `CHANGELOG.md`
- Modify: `docs/versioning.md`

- [ ] **Step 1: Write the failing release-version contract**

Change `tests/test_release_version_policy.py` so `test_package_version_matches_v050_release` expects `0.5.5`:

```python
def test_package_version_matches_v050_release():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == "0.5.5"
```

- [ ] **Step 2: Run the focused release policy test**

Run: `uv run pytest tests/test_release_version_policy.py -q`

Expected: fail because `pyproject.toml` still reports `0.5.4`.

- [ ] **Step 3: Update release metadata**

Set `pyproject.toml` project version to `0.5.5`, run `uv lock`, add `## v0.5.5 - 2026-06-10` under `CHANGELOG.md` `Unreleased`, and update `docs/versioning.md` so the current package release and matching tag are `v0.5.5`.

- [ ] **Step 4: Re-run focused release policy tests**

Run: `uv run pytest tests/test_release_version_policy.py -q`

Expected: all release policy tests pass.

### Task 2: Release Verification And Landing

**Files:**
- Release metadata files from Task 1

- [ ] **Step 1: Run full local verification**

Run: `make verify`

Expected: disk preflight, actionlint, ruff, format check, mypy, docs drift, pytest, build, and release health all pass.

- [ ] **Step 2: Run release tag dry-run**

Run: `uv run python scripts/verify_release_tag.py --tag v0.5.5`

Expected: prints that `v0.5.5` matches `pyproject.toml` version `0.5.5`.

- [ ] **Step 3: Open and merge release PR**

Push `release/0.5.5`, create a PR titled `Prepare 0.5.5 release`, update PR verification with `PR_NUMBER=<pr> make pr-verification`, wait for hosted CI, then merge after checks pass.

### Task 3: Tag And Verify Published Release

**Files:**
- No source file changes expected

- [ ] **Step 1: Create and push annotated tag**

Run:

```bash
git switch main
git pull --ff-only
git tag -a v0.5.5 -m "v0.5.5"
git push origin v0.5.5
```

- [ ] **Step 2: Watch release workflow**

Run:

```bash
gh run list --workflow Release --limit 3
gh run watch <run-id> --interval 10
```

Expected: Release workflow passes.

- [ ] **Step 3: Verify GitHub Release assets**

Run:

```bash
gh release view v0.5.5 --json tagName,name,isDraft,isPrerelease,url,assets
uv run python scripts/verify_release_assets.py --tag v0.5.5 --repo uesugitorachiyo/agy-swarms
```

Expected: release is non-draft, non-prerelease, includes wheel, source distribution, and `SHA256SUMS.txt`; asset verifier reports the wheel and source distribution as verified.
