# agy-swarms Reference Task

## Purpose

This is the pinned Phase-0 reference task used for baseline harvest, AC-2 comparisons, M3 wall-clock comparisons, and AC-CON7 clean-checkout execution.

## Task

Implement a small deterministic bug fix in a Python package:

1. Read a function that merges two structured result dictionaries.
2. Preserve deterministic key ordering.
3. Reject conflicting scalar values with a typed error.
4. Add tests for happy path, nested merge, scalar conflict, and deterministic output ordering.
5. Run the test suite and report the exact command and result.

## Constraints

- Do not use external services.
- Do not write outside the repository.
- Do not depend on sibling repositories.
- Return a concise patch summary, test output, and any unresolved concerns.

## Hashing

`reference_task_sha` is the SHA-256 of this file's bytes and is recorded in `agy.lock` during Phase 0.
