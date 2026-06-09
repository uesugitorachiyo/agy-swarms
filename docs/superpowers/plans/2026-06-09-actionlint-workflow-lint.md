# Actionlint Workflow Lint Plan

## Goal

Catch GitHub Actions workflow syntax and expression mistakes in local and hosted
verification before jobs reach runtime.

## Scope

- Add `actionlint-py` to the development dependency set.
- Add a `workflow-lint` Makefile target that runs `actionlint`.
- Include `workflow-lint` in `verify-fast`, which is already used by local
  release verification, CI matrix checks, and the release publishing workflow.
- Add contract tests for the Makefile target, dependency, and documentation.
- Document workflow linting in release verification and architecture docs.

## Verification

- `uv run python -m pytest tests/test_quality_command_contracts.py -q`
- `make workflow-lint`
- `make verify`
