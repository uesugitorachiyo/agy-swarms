# Architecture

`agy-swarms` keeps the runtime deterministic by separating command parsing,
orchestration, mechanical helper logic, and release verification.

## CLI And Commands

`agy_swarms/main.py` is the console entrypoint wrapper. It delegates parser
construction and dispatch to `agy_swarms/cli.py`.

Command bodies live under `agy_swarms/commands/`. Each command module owns one
CLI surface or a closely related pair of surfaces:

- `agy_swarms/commands/run.py` owns graph/task execution commands.
- `agy_swarms/commands/preflight.py` owns read-only graph preflight.
- `agy_swarms/commands/inspect.py` and `agy_swarms/commands/resume.py` own saved-report inspection and resume summaries.
- `agy_swarms/commands/inspect_bundle.py`, `agy_swarms/commands/report_summary.py`, and `agy_swarms/commands/review.py` own review-bundle and review-routing commands.
- `agy_swarms/commands/install.py` owns local install helper commands.

`agy_swarms/commands/_legacy.py` is a compatibility re-export module. New command
logic should go into focused command modules, not back into `agy_swarms/main.py`.

## Conductor

`agy_swarms/conductor.py` is the deterministic orchestration spine. It owns graph
run order, scheduler transitions, high-level retry/fallback decisions, blocker
creation, and the public `run()`, `agent(...)`, and `pipeline(...)` entrypoints.

The conductor should make policy decisions, then delegate mechanical work to
helpers. Keep behavior that requires full orchestration context in the conductor:
ready-set selection, budget-stop decisions, adapter choice, fallback eligibility,
checkpoint lifecycle, and report assembly.

## Conductor Helpers

Helper modules keep repeated mechanics type-checkable and easier to review:

- `agy_swarms/conductor_budget.py` converts consumed-budget mappings, computes actual usage from envelopes, and commits actual usage to the ledger/runtime state.
- `agy_swarms/conductor_checkpointing.py` owns checkpoint cache predicates, runtime hydration from journal hits, journal-entry builders, and pipeline stage keys.
- `agy_swarms/conductor_commands.py` runs local command nodes through the command runner abstraction.
- `agy_swarms/conductor_drift.py` adapts optional conductor lockfiles to `validate.check_drift(...)` and copies drift records for reports.
- `agy_swarms/conductor_fallback.py` owns fallback adapter selection, model-switch event construction, and the mechanical fallback dispatch attempt.
- `agy_swarms/conductor_pipeline.py` owns per-item staged pipeline execution while receiving conductor-owned callbacks for cache, journal, key, and classification behavior.
- `agy_swarms/conductor_reports.py` defines `RunReport` and `PipelineItemResult`.
- `agy_swarms/conductor_review.py` dispatches reviewer and closer nodes through review routing.
- `agy_swarms/conductor_review_budget.py` builds review budget alert and closer auto-triage events.

When adding conductor behavior, prefer this split:

- Put policy and ordering decisions in `agy_swarms/conductor.py`.
- Put repeated pure or mechanical transformations in a `agy_swarms/conductor_*.py` helper.
- Add focused helper tests before wiring the conductor to the helper.
- Add new helper modules to the `make type-check` target.

## Release Health

Release verification is split between a registry, renderer, and runner:

- `scripts/release_health_registry.py` is the source of truth for release-health probe definitions.
- `scripts/release_health.py` runs the registered probes and prints the dashboard.
- `scripts/release_health_docs.py` renders probe documentation from the registry.
- `scripts/rewrite_release_health_docs.py` rewrites the generated probe block in `docs/release-verification.md`.

The CI workflow also runs `make verify` in a clean checkout. Locally, `make verify`
includes a strict docs drift check, so individual verification commands can be
more convenient while a working tree intentionally contains uncommitted changes.

## Verification Facade

The Makefile defines the project verification facade:

- `make lint`
- `make format-check`
- `make type-check`
- `make test`
- `make build`
- `make release-health`
- `make verify-docs`
- `make verify`

`make type-check` intentionally lists currently clean modules explicitly. When a
module becomes mypy-clean, add it to the target and protect that coverage with a
contract test.
