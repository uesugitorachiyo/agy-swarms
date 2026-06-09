# Release Operator Checklist

## Goal

Add one documented operator path for cutting package releases so version,
changelog, verification, tagging, GitHub Release publication, and evidence
capture happen in a repeatable order.

## Plan

1. Add failing release policy tests that require a checklist document and links
   from existing release docs.
2. Add `docs/release-operator-checklist.md` with the end-to-end release flow.
3. Link the checklist from README, versioning policy, and release verification
   docs.
4. Record the documentation update in the changelog.
5. Run focused release-policy tests and the full local verification gate.

## Verification

- `uv run python -m pytest tests/test_release_version_policy.py -q`
- `make verify`
