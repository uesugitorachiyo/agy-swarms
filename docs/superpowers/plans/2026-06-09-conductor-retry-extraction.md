# Conductor Retry Extraction Plan

## Goal

Continue shrinking `agy_swarms/conductor.py` by moving the self-contained
failure classification and retry eligibility policy into a focused helper module.

## Scope

- Add `agy_swarms/conductor_retry.py` for `classify` and `retry_eligible`.
- Keep `agy_swarms.conductor` re-export compatibility for existing callers.
- Add helper contract coverage in `tests/test_conductor_helpers.py`.
- Update architecture docs and contracts for the new helper boundary.

## Verification

- `uv run python -m pytest tests/test_conductor_helpers.py tests/test_conductor.py tests/test_quality_command_contracts.py -q`
- `make verify`
