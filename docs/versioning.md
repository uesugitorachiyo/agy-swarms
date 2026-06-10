# Versioning Policy

The project uses milestone tags and package versions for different jobs.

## Current milestone

`v0.0.0-ac0-ac6` is the frozen milestone tag for the verified AC0-AC6 baseline.
Do not retag or move it. New release-engineering work happens after that milestone
on `main`.

## Current package release

The current package version is `0.5.6`, released after the GitHub Release
workflow gained a post-publish asset self-check, cross-platform checksum
verification, automatic pull requests and pushes to `main`, and conductor
accounting helper extraction. The matching release tag is `v0.5.6`.

Before the release cut, the package stayed at `0.0.0` while release mechanics,
documentation, CI-safe checks, and packaging smoke tests were hardened.

The previous package release was `0.5.5`, with matching release tag `v0.5.5`.

## Future release gate

Before changing `pyproject.toml` to a new release version or creating a new release
tag, run and review:

```bash
uv run python scripts/release_health.py
uv build
```

The release health suite includes the deterministic acceptance probes and
`scripts/fresh_clone_smoke.py`. The v0.2 gate also includes
`scripts/v02_local_runner_probe.py`; the v0.4 gate also includes
`scripts/v04_fixture_replay_probe.py`; the v0.5 gate also includes
`scripts/v05_report_contract_probe.py`. These checks are expected to leave
`git status --short` clean.

GitHub Actions now runs automatically for pull requests and pushes to `main`.
Local `make verify` remains the pre-PR release gate, and remote CI is the hosted
release authority once a pull request or `main` push starts. Keep
`workflow_dispatch` available for manual reruns after infrastructure failures.
The expected `main` branch protection policy lives in
`.github/branch-protection.json` and is documented in `docs/branch-protection.md`.

After a release tag is pushed, `.github/workflows/release.yml` verifies the tag
against `pyproject.toml` with `scripts/verify_release_tag.py`, runs
`make verify`, rebuilds the wheel and source distribution, and publishes them as
GitHub Release artifacts with generated notes.

Use `docs/release-operator-checklist.md` for the end-to-end release sequence:
version bump, changelog, lockfile, local verification, pull request checks, tag,
GitHub Release publication, and final evidence capture.
