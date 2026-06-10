# Release 0.5.4 Readiness Implementation Plan

**Goal:** Prepare the hosted-release, CI-policy, and conductor-modularization
work as package release `0.5.4`.

**Architecture:** Treat this as a patch release: update package metadata and
lockfile version, move accumulated changelog entries into a dated `v0.5.4`
section, refresh release docs, verify locally, then use the normal PR, tag, and
GitHub Release flow.

## Acceptance Criteria

- `pyproject.toml` version `0.5.4`
- `uv.lock` package entry for `agy-swarms` version `0.5.4`
- `CHANGELOG.md` section `## v0.5.4 - 2026-06-10`
- Release docs reference the current Windows runner label
- Local `make verify` passes before pull request review
- Pull request CI and post-merge `main` CI pass
- Annotated tag `v0.5.4` publishes GitHub Release assets

## Verification

```bash
uv run python -m pytest tests/test_release_version_policy.py -q
uv run python scripts/verify_release_tag.py --tag v0.5.4
make verify
gh pr checks <pr> --watch --interval 10
gh run watch <main-ci-run> --interval 10
gh run watch <release-run> --interval 10
gh release view v0.5.4 --json tagName,name,isDraft,isPrerelease,url,assets
```
