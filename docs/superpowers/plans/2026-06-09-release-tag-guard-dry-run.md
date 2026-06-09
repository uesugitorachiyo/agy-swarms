# Release Tag Guard Dry Run Plan

## Goal

Make the GitHub Release workflow's tag/version guard testable outside GitHub
Actions so a bad release tag can be caught by local tests before publication.

## Scope

- Extract the release tag comparison into `scripts/verify_release_tag.py`.
- Update `.github/workflows/release.yml` to call the tested script.
- Add unit and CLI tests for matching and mismatched tags.
- Include the script in the Makefile type-check target.
- Document the guard in release verification and operator docs.

## Verification

- `uv run python -m pytest tests/test_release_tag_guard.py tests/test_ci_workflow.py tests/test_quality_command_contracts.py -q`
- `make verify`
