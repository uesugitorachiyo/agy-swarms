# Pin Windows CI Runner

## Goal

Remove ambiguity from the Windows CI leg by replacing the floating
`windows-latest` label with an explicit supported Windows runner label and
keeping branch protection synchronized with the resulting check name.

## Plan

1. Add failing tests that require `windows-2025` and reject `windows-latest` in
   the current CI workflow.
2. Update `.github/workflows/ci.yml` to run the Windows matrix leg on
   `windows-2025`.
3. Update `.github/branch-protection.json` and `docs/branch-protection.md` so
   required status checks match the new matrix-expanded check name.
4. Update release docs, README, and release policy tests.
5. Run focused tests and the full local verification gate.
6. Merge through PR CI and update live GitHub branch protection.

## Verification

- `uv run python -m pytest tests/test_ci_workflow.py tests/test_release_version_policy.py -q`
- `make verify`
