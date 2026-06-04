# Versioning Policy

The project uses milestone tags and package versions for different jobs.

## Current milestone

`v0.0.0-ac0-ac6` is the frozen milestone tag for the verified AC0-AC6 baseline.
Do not retag or move it. New release-engineering work happens after that milestone
on `main`.

## Current package release

The current package version is `0.5.1`, released after hybrid review-routing,
plugin installation smoke coverage, and terminal encoding fixes landed. The
matching release tag is `v0.5.1`.

Before the release cut, the package stayed at `0.0.0` while release mechanics,
documentation, CI-safe checks, and packaging smoke tests were hardened.

The previous package release was `0.5.0`, with matching release tag `v0.5.0`.

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

GitHub Actions is configured as manual-only while billing is postponed. Until
billing is resolved, local `scripts/release_health.py` output is the release
authority.
