# GitHub Release Workflow

## Goal

Publish GitHub Release artifacts automatically from version tags while keeping
the release gate deterministic and documented.

## Plan

1. Add failing workflow contract tests for the release trigger, verification
   command, artifact upload, generated notes, and operator docs.
2. Add `.github/workflows/release.yml` for `v*` tags and manual reruns with an
   existing tag.
3. Verify the tag matches the package version before publishing.
4. Run `make verify`, rebuild `dist/`, and create the GitHub Release with wheel
   and source distribution artifacts.
5. Update README, release verification docs, versioning policy, and changelog.

## Verification

- `uv run python -m pytest tests/test_ci_workflow.py -q`
- `make verify`
