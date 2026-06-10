# Windows Runner VS2026 Policy Plan

## Goal

Update CI and branch-protection policy to use GitHub's redirected Windows 2025
hosted runner label before the June 15, 2026 transition.

## Scope

- Change the CI matrix Windows leg from `windows-2025` to
  `windows-2025-vs2026`.
- Update `.github/branch-protection.json` so required status checks match the
  new matrix-expanded check name.
- Update branch-protection and release verification docs.
- Keep workflow contract tests synchronized with the policy.

## Verification

- `uv run python -m pytest tests/test_ci_workflow.py -q`
- `make verify`
