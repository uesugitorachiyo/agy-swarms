# Branch Protection Policy

## Goal

Record the expected `main` branch protection rules in the repository and make
the required hosted merge checks testable against the CI workflow.

## Plan

1. Add tests that fail when the branch-protection policy or documentation is
   missing.
2. Add a machine-readable `.github/branch-protection.json` policy for `main`.
3. Document the GitHub branch settings operators should mirror from the policy.
4. Link the policy from release-facing docs.
5. Run focused CI workflow tests and the full local verification gate.

## Verification

- `uv run python -m pytest tests/test_ci_workflow.py -q`
- `make verify`
