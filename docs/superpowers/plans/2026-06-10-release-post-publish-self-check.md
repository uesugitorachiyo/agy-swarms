# Release Post-Publish Self-Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Release workflow verify the GitHub Release assets it just published.

**Architecture:** Add a post-publish workflow step after `gh release create` that runs the existing Python verifier against `$RELEASE_TAG`. Protect the workflow contract with tests that check the verifier step exists and runs after publication, then update release docs to describe the automated self-check.

**Tech Stack:** GitHub Actions, GitHub CLI, Python release scripts, pytest workflow contract tests.

---

### Task 1: Workflow Contract

**Files:**
- Modify: `tests/test_ci_workflow.py`

- [ ] **Step 1: Write the failing workflow contract**

Add this test:

```python
def test_release_workflow_self_checks_published_assets_after_publish():
    workflow = _release_workflow_text()

    publish_index = workflow.index("gh release create")
    verify_index = workflow.index("scripts/verify_release_assets.py")

    assert "Verify Published Release Assets" in workflow
    assert 'GH_TOKEN: ${{ github.token }}' in workflow
    assert '--tag "$RELEASE_TAG"' in workflow
    assert "--repo uesugitorachiyo/agy-swarms" in workflow
    assert publish_index < verify_index
```

- [ ] **Step 2: Run the focused test**

Run: `uv run pytest tests/test_ci_workflow.py::test_release_workflow_self_checks_published_assets_after_publish -q`

Expected: fail because the Release workflow does not yet run `scripts/verify_release_assets.py`.

### Task 2: Release Workflow And Docs

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `docs/release-verification.md`

- [ ] **Step 1: Add the self-check workflow step**

Add this step immediately after `Publish GitHub Release`:

```yaml
      - name: Verify Published Release Assets
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          uv run python scripts/verify_release_assets.py \
            --tag "$RELEASE_TAG" \
            --repo uesugitorachiyo/agy-swarms
```

- [ ] **Step 2: Update release docs**

Update `docs/release-verification.md` so the GitHub Release publishing section says the workflow verifies the published assets after `gh release create`.

- [ ] **Step 3: Run focused tests**

Run: `uv run pytest tests/test_ci_workflow.py::test_release_workflow_verifies_and_attaches_package_artifacts tests/test_ci_workflow.py::test_release_workflow_self_checks_published_assets_after_publish tests/test_ci_workflow.py::test_release_docs_explain_github_release_publishing -q`

Expected: all focused workflow and docs tests pass.

### Task 3: Full Verification And Landing

**Files:**
- All files from Tasks 1 and 2

- [ ] **Step 1: Run full local verification**

Run: `make verify`

Expected: disk preflight, actionlint, ruff, format check, mypy, docs drift, pytest, build, and release health all pass.

- [ ] **Step 2: Review and land**

Run `codex review --uncommitted`, fix any actionable findings, then commit, open a PR, watch hosted CI, merge, and watch post-merge `main` CI.
