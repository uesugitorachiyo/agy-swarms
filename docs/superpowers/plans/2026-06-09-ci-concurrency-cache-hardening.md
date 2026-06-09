# CI Concurrency And Cache Hardening

## Goal

Reduce duplicate GitHub Actions work and non-fatal uv cache reservation noise
without weakening `main` or release evidence.

## Plan

1. Add failing workflow contract tests for CI concurrency, release publication
   serialization, and explicit uv cache-save policy.
2. Add top-level CI concurrency that cancels superseded pull request runs but
   leaves `main` push runs uncanceled.
3. Give each CI `setup-uv` use a distinct cache suffix and save caches only from
   `main` runs.
4. Serialize release publishing per tag and keep the release workflow from
   writing tag-specific uv cache entries.
5. Document the policy and verify locally plus in hosted CI.

## Verification

- `uv run python -m pytest tests/test_ci_workflow.py -q`
- `make verify`
