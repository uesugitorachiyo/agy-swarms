# Branch Protection

`.github/branch-protection.json` is the repository-local source of truth for
the expected `main` branch merge gate. GitHub does not automatically consume
this file; repository administrators should mirror it in the GitHub branch
protection settings for `main`.

## Required `main` Settings

- Require branches to be up to date before merging.
- Require at least 1 approving review before merging.
- Dismiss stale pull request approvals when new commits are pushed.
- Require conversation resolution before merging.
- Require the status checks listed below to pass.
- Block merges unless required checks pass, and block force pushes and branch deletion.

The required status checks are:

- `Fast Checks (ubuntu-latest)`
- `Fast Checks (macos-latest)`
- `Fast Checks (windows-latest)`
- `Verify Package Install Modes`
- `Release Health`

Keep these names synchronized with `.github/workflows/ci.yml`. Matrix-expanded
check names must match the check runs reported by GitHub, not only the compact
workflow job id.

## Operator Check

Before merging a release-prep or CI change, confirm that the pull request has
green checks for each required context and that the post-merge `main` push also
finishes green. Local `make verify` remains the pre-PR gate; branch protection is
the hosted merge gate.
