# Conductor Codex Batch Extraction Plan

## Goal

Continue shrinking `agy_swarms/conductor.py` by moving the Codex review batch
eligibility and dispatch mechanics into a focused helper module.

## Scope

- Add `agy_swarms/conductor_codex_batch.py`.
- Keep `Conductor._dispatch_codex_review_batch()` as a thin delegate so run-loop
  behavior stays unchanged.
- Add helper and architecture contract tests.
- Preserve the existing parallel Codex review behavior test.

## Verification

- `uv run python -m pytest tests/test_conductor_helpers.py tests/test_hybrid_review.py tests/test_quality_command_contracts.py -q`
- `make verify`
