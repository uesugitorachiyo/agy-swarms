# agy-swarms Archive Handoff

`agy-swarms` is out of active AO Foundry scope as of 2026-06-23. The repository
is kept as a reference implementation for deterministic local graph execution,
review routing, and release verification patterns.

## Archive State

- Local `main` was clean and aligned with `origin/main` before this handoff.
- No open GitHub pull requests were present during the archive audit.
- The latest release tag observed during the handoff was `v0.5.6`.
- Future changes should be limited to security, archival notes, or deliberate
  extraction into active AO spine repositories.

## Reusable Extraction Targets

- Deterministic graph execution: `agy_swarms/conductor.py`,
  `agy_swarms/scheduler.py`, `agy_swarms/graph_io.py`, and
  `agy_swarms/graph_store.py`.
- Command review and guarded local execution:
  `agy_swarms/review_bundle.py`, `agy_swarms/review_bundle_guard.py`,
  `agy_swarms/commands/review.py`, and the local-runner schemas in `schemas/`.
- Checkpointed evidence and resume flows: `agy_swarms/checkpoint.py`,
  `agy_swarms/commands/inspect.py`, `agy_swarms/commands/resume.py`, and
  `agy_swarms/conductor_checkpointing.py`.
- Review routing policy and benchmark ideas: `agy_swarms/review_routing_policy.py`,
  `agy_swarms/hybrid_review.py`, `agy_swarms/model_routing.py`, and
  `benchmarks/review_routing_performance.md`.
- Release verification facade: `Makefile`, `scripts/release_health.py`,
  `scripts/release_health_registry.py`, `docs/release-verification.md`, and
  `.github/workflows/ci.yml`.

## AO Spine Routing

- Put portfolio and evidence-loop decisions in `ao-foundry`.
- Put planning, gating, and run orchestration in `ao-forge`.
- Put provider-free execution and SDD command surfaces in `ao2`.
- Put readback and retention visibility in `ao2-control-plane`.
- Put policy evaluation and fail-closed gates in `ao-covenant`.

## Do Not Carry Forward

- Do not make `agy-swarms` a required preflight dependency for AO Foundry.
- Do not start new feature branches here unless they are explicitly for archive
  hygiene or extraction into the active AO spine.
- Do not restore subscription-dependent workflows without a new portfolio
  decision in `ao-foundry`.
