# Changelog

All notable release-engineering milestones for this repository are recorded here.

## Unreleased

- Added a repository-local branch-protection policy and docs for the required
  `main` merge gate.
- Added a tag-driven GitHub Release publishing workflow for wheel and source
  distribution artifacts.
- Pinned Windows CI to `windows-2025` and updated the required merge check name
  to avoid the floating `windows-latest` runner redirect.
- Added workflow concurrency and uv cache-save policy to cancel superseded pull
  request CI runs while preserving `main` and release evidence.
- Added a release operator checklist covering version bump, changelog, tag,
  GitHub Release publication, and verification evidence.
- Added a tested release tag/version guard script used by the GitHub Release
  workflow before publishing artifacts.

## v0.5.3 - 2026-06-09

This release packages the repository-hardening work that made local and hosted
verification reliable enough to run automatically on pull requests and `main`.

- Clarified Antigravity plugin installation docs: the supported public path is
  fresh clone plus `agy plugin install .`; raw GitHub URL install targets are
  rejected by `agy` 1.0.5 as unsupported extension formats.
- Added a verification disk preflight before heavy Make targets so low-space
  environments fail early with `AGY_VERIFY_MIN_FREE_MIB` and `TMPDIR` guidance.
- Enabled automatic pull-request and `main` push CI while keeping
  `workflow_dispatch` available for manual reruns.
- Hardened the PR verification updater so unmarked or duplicate verification
  sections are replaced cleanly.
- Split fast matrix checks from release-health and verified the release gate
  locally with `723 passed` plus release health `24/24 checks passed`.
- Confirmed automatic remote CI on the release-prep path across Ubuntu, macOS,
  Windows, package install modes, and release health.

## v0.5.2 - 2026-06-05

This release makes Codex reviewer/closer routing functional and adds calibration
tools for the hybrid review workflow.

- Replaced route-only Codex reviewer/closer handling with read-only Codex CLI
  execution, structured reviewer/closer schemas, and role-specific model
  configuration.
- Added review telemetry and seeded review benchmark support for comparing
  `codex-low` and `codex-high` behavior.
- Added conservative Codex review batching outside checkpointed runs and
  documented the checkpoint journal design needed before enabling checkpointed
  batches.
- Added telemetry-driven route recommendations for choosing Codex low/high
  effort from observed review outcomes.

## v0.5.1 - 2026-06-03

This release introduces hybrid review-routing capabilities, expands plugin installation verification, and fixes cross-platform terminal encoding crashes.

- Added **Hybrid Review-Routing (v0.21)** slice support, allowing developers to route the `reviewer` and `closer` nodes to different adapters (`agy`, `codex`, `claude`, or `off`).
- Added the `review-route` subcommand to preview reviewer/closer routing paths without provider execution.
- Added `scripts/plugin_smoke_probe.py` (`V22 Plugin Installation Smoke`) to automate local installation, listing, and uninstallation of `agy-swarms` as an `agy` CLI plugin.
- Fixed terminal encoding crashes on Windows (CP1252/charmap) by replacing Unicode checkmark symbols (`✔`) with standard ASCII `[OK]`.
- Implemented a comparative benchmark script `benchmarks/benchmark_review_routing.py` to evaluate performance, token consumption, and routing fidelity across all adapters.

## v0.5.0 - 2026-06-01

This release cuts the v0.5 Local Runner Report Contracts milestone into package
version `0.5.0`.

- Added `schemas/local-runner-report-v1.schema.json` for stable saved
  local-runner report evidence.
- Added `scripts/v05_report_contract_probe.py` to replay tracked local-runner
  fixtures, validate saved reports, and verify inspect/resume summary contracts.
- Wired the v0.5 report contract probe into local release health.
- Documented the billing-free report-contract workflow for operators.

## v0.4.0 - 2026-06-01

This release cuts the v0.3 local runner hardening and v0.4 Local Runner Replay Fixtures
milestone into package version `0.4.0`.

- Added strict command-array graph intake and redacted graph-load diagnostics.
- Added deterministic report summaries shared by `inspect` and saved-report
  `resume`.
- Added tracked success, failure, and dependency-skip local-runner graph
  fixtures.
- Added `scripts/v04_fixture_replay_probe.py` to replay tracked fixtures,
  inspect saved reports, and prove saved-report resume does not rerun local
  command nodes.
- Wired the v0.4 fixture replay probe into local release health.
- Expanded release verification docs for billing-free fixture replay and saved
  report triage.

## v0.2.0 - 2026-05-31

This release cuts the v0.2 Local Runner MVP into package version `0.2.0`.

- Added graph-file intake for operator-supplied `TaskGraph` JSON.
- Added deterministic local command graph execution through the existing conductor.
- Added stable JSON run reports and `run --graph --report` CLI support.
- Added report-aware `inspect` / `resume` behavior for local runner artifacts.
- Added a read-only `agy` review handoff prompt.
- Added `scripts/v02_local_runner_probe.py` and wired it into release health as
  the AC-7/AC-8/AC-9 local runner gate.

## v0.1.0 - 2026-05-31

This release cuts the completed v0.1 release engineering work into package
version `0.1.0`.

- Added a non-mutating release health command for local and future CI use:
  `uv run python scripts/release_health.py`.
- Added a manual-only GitHub Actions workflow. GitHub Actions billing is currently
  postponed, so local release health remains the authoritative gate.
- Added a fresh-clone install smoke that verifies `uv sync --extra dev`, importability,
  CLI entrypoint wiring, and clean clone state.
- Tightened packaging metadata so the wheel contains only the `agy_swarms` package.
- Documented the release verification split between CI-safe deterministic checks and
  local-live `agy` OAuth probes.
- Documented and executed the versioning policy: hold `0.0.0` during v0.1 release
  engineering, then cut `0.1.0` only after the release gate passed.

## v0.0.0-ac0-ac6 - 2026-05-31

- Frozen AC0-AC6 milestone tag for the Phase 0 through Phase 6 implementation.
- Preserves the verified baseline where acceptance probes AC-0 through AC-6 pass.
- Establishes the review baseline for subsequent v0.1 release-engineering work.
