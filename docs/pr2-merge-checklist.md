# PR #2 Merge Checklist

Use this checklist before landing PR #2, `Harden verification and split core modules`.

## Pre-Merge

- Confirm the branch is current:

```bash
git switch codex/repo-hardening-refactor
git status -sb
git fetch origin
```

- Run the full local verification gate:

```bash
make verify
```

- Refresh PR evidence after the final verified commit:

```bash
make pr-verification PR_NUMBER=2
```

- Check remote CI and status checks. If GitHub Actions jobs appear, wait for all remote CI status checks to pass before merging:

```bash
gh pr view 2 --json mergeable,statusCheckRollup,url
gh run list --branch codex/repo-hardening-refactor --limit 10
```

- Confirm the PR is still mergeable:

```bash
gh pr view 2 --json mergeable,state,headRefOid
```

## Merge

- Use a merge strategy that preserves the reviewable sequence unless a reviewer explicitly asks for a squash:

```bash
gh pr merge 2 --merge
```

- If the branch is intentionally squashed instead, preserve the major commit-group summary in the squash body.

- This PR is repository hardening, not a package release. The default landing policy is no release tag and no version bump unless that decision is made explicitly before merge.

## Post-Merge

- Sync the local default branch:

```bash
git switch main
git pull --ff-only
```

- Confirm the merged default branch still verifies locally when time allows:

```bash
make verify-fast
```

- Leave `codex/repo-hardening-refactor` until PR #2 is fully reviewed post-merge; delete it only after confirming no follow-up work is needed from the branch.
