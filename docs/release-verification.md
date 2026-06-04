# Release Verification

This project has two verification surfaces:

- **CI-safe release health:** deterministic checks that do not require local `agy` OAuth, Gemini API keys, network model calls, or writable evidence files.
- **Local-live `agy` probes:** historical Phase 0 transport probes that intentionally shell out to the local Antigravity `agy` CLI and require authenticated local state.

## CI-safe release health

Use this command for routine local release checks and for CI once GitHub Actions billing is available:

```bash
uv run python scripts/release_health.py
```

For unattended shells such as `codex-cron`, make sure `uv` is discoverable before
running verification commands:

```bash
export PATH="$HOME/.local/bin:$PATH"
uv run pytest -q
uv run python scripts/release_health.py
```

This is only a local tool-path requirement. It does not require GitHub Actions,
provider API keys, local `agy` OAuth, or live model billing.

## Local runner report evidence

For billing-free local runner reports, inspect saved JSON evidence without
rerunning commands:

```bash
agy inspect --checkpoint path/to/report.json
agy resume --checkpoint path/to/report.json
```

Both commands include the same stable `summary` object:

```json
{
  "total_nodes": 3,
  "status_counts": {"failed": 1, "skipped": 1, "succeeded": 1},
  "failed_nodes": ["unit"],
  "skipped_nodes": ["integration"],
  "blocker_count": 1,
  "concern_count": 1,
  "changed_files_count": 1
}
```

`inspect` classifies the file as a saved run report. `resume` loads the same
report evidence and does not rerun local command nodes, so operators can confirm
failure and skipped-node evidence before deciding whether to launch a new run.

## Local runner fixture replay

Use the tracked fixture suite when you need a billing-free replay check for the
local runner from a fresh checkout. The focused probe runs the success, failure,
and dependency-skip fixtures, writes reports to a temporary directory, inspects
the saved reports, and confirms `resume_loaded` evidence without rerunning local
command nodes:

```bash
uv run python scripts/v04_fixture_replay_probe.py
```

The fixtures live at:

- `tests/fixtures/local_runner/success-graph.json`
- `tests/fixtures/local_runner/failure-graph.json`
- `tests/fixtures/local_runner/dependency-skip-graph.json`

To inspect one fixture manually, write the report to an operator-owned temporary
path:

```bash
uv run agy-swarms run --graph tests/fixtures/local_runner/success-graph.json --allow-local-commands --report /tmp/agy-v04-success-report.json
uv run agy-swarms inspect --checkpoint /tmp/agy-v04-success-report.json
uv run agy-swarms resume --checkpoint /tmp/agy-v04-success-report.json
```

The failure and dependency-skip fixtures are expected to return non-zero from
`run --graph`; inspect their saved reports after the run to review failed and
skipped-node evidence:

```bash
uv run agy-swarms run --graph tests/fixtures/local_runner/failure-graph.json --allow-local-commands --report /tmp/agy-v04-failure-report.json
uv run agy-swarms inspect --checkpoint /tmp/agy-v04-failure-report.json
uv run agy-swarms resume --checkpoint /tmp/agy-v04-failure-report.json

uv run agy-swarms run --graph tests/fixtures/local_runner/dependency-skip-graph.json --allow-local-commands --report /tmp/agy-v04-dependency-skip-report.json
uv run agy-swarms inspect --checkpoint /tmp/agy-v04-dependency-skip-report.json
uv run agy-swarms resume --checkpoint /tmp/agy-v04-dependency-skip-report.json
```

This replay path uses only local deterministic commands. It does not require
GitHub Actions, provider API keys, local `agy` OAuth, live `agy` calls, or model
billing, and generated reports should stay outside the repository unless a
future milestone explicitly promotes a stable artifact.

The release health command runs:

- `uv run ruff check .`
- `uv run pytest -q`
- `scripts/fresh_clone_smoke.py`
- `scripts/v02_local_runner_probe.py`
- `scripts/v04_fixture_replay_probe.py`
- `scripts/v05_report_contract_probe.py`
- `scripts/v06_graph_preflight_probe.py`
- `scripts/v07_preflight_contract_probe.py`
- `scripts/v08_command_review_probe.py`
- `scripts/v09_command_review_contract_probe.py`
- `scripts/v10_review_bundle_probe.py`
- `scripts/v11_review_bundle_inspection_probe.py`
- `scripts/v12_review_bundle_diff_probe.py`
- `scripts/v13_review_bundle_run_guard_probe.py`
- `scripts/v14_guarded_run_provenance_probe.py`
- `scripts/v15_guarded_report_inspection_probe.py`
- `scripts/v16_saved_report_summary_contract_probe.py`
- `scripts/v17_guarded_report_contract_probe.py`
- `scripts/v18_guarded_failure_report_contract_probe.py`
- `scripts/v19_guard_rejection_report_contract_probe.py`
- `scripts/v20_guard_rejection_inspection_probe.py`
- `scripts/v21_hybrid_review_routing_probe.py`

These checks are expected to leave `git status --short` clean.

`GEMINI_API_KEY` is not required for this path. Local `agy` OAuth is also not required.

## Local graph preflight

Use the v0.6 graph preflight workflow when you need to validate and inspect an
operator-supplied local runner graph before deciding whether to run it:

```bash
uv run agy-swarms preflight --graph tests/fixtures/local_runner/success-graph.json
```

The preflight command reuses the same graph intake and redacted validation path
as `run --graph`, but it does not execute command nodes and does not require
`--allow-local-commands`. Its JSON output reports stable graph-shape metadata:
`status`, `node_count`, `edge_count`, `role_counts`, `command_node_ids`,
`root_nodes`, `leaf_nodes`, dependency fan-out details, and
`commands_executed: false`.

For the focused billing-free fixture gate, run:

```bash
uv run python scripts/v06_graph_preflight_probe.py
```

The probe preflights the tracked success, failure, and dependency-skip local
runner fixtures and confirms every case reports `commands_executed: false`.
This path requires no API keys, no live `agy`, no GitHub Actions billing, no
provider calls, and no model billing.

## Local graph preflight contracts

Use the v0.7 graph preflight contract gate when you need machine-checkable JSON
evidence for `agy-swarms preflight --graph` output before approving local
command execution. The tracked schema lives at:

- `schemas/local-graph-preflight-v1.schema.json`

The focused contract probe preflights the success, failure, and dependency-skip
fixtures, validates each payload against the schema contract, and confirms the
preflight path does not execute command nodes:

```bash
uv run python scripts/v07_preflight_contract_probe.py
```

The schema covers `status`, `node_count`, `edge_count`, `role_counts`,
`command_node_ids`, `root_nodes`, `leaf_nodes`, `dependency_fan_out`, and the
`commands_executed: false` no-execution signal. This path uses only local
deterministic graph validation: no API keys, no live `agy`, no GitHub Actions
billing, no provider calls, and no model billing.

## Local command review evidence

Use the v0.8 command review workflow when you need to inspect the planned local
command surface before granting command execution. The `--command-review` flag
is opt-in, so default v0.7 `preflight --graph` output remains stable for the
tracked preflight schema contract:

```bash
uv run agy-swarms preflight --graph tests/fixtures/local_runner/success-graph.json --command-review
```

The command review payload is keyed by command node id and includes redacted
argv previews, executable metadata, argv counts, and raw argv SHA-256 digests.
It does not execute command nodes and does not require
`--allow-local-commands`.

For the focused billing-free fixture gate, run:

```bash
uv run python scripts/v08_command_review_probe.py
```

The probe preflights the tracked success, failure, and dependency-skip fixtures
with `--command-review`, verifies every command node has review evidence, and
confirms `commands_executed: false`. This path uses only local deterministic
graph validation: no API keys, no live `agy`, no GitHub Actions billing, no
provider calls, and no model billing.

## Command review contracts

Use the v0.9 command review contract gate when you need machine-checkable JSON
evidence for opt-in `agy-swarms preflight --graph --command-review` output.
The tracked schema lives at:

- `schemas/local-command-review-v1.schema.json`

The focused contract probe preflights the success, failure, and dependency-skip
fixtures with `--command-review`, validates the command review payload, verifies
every command node has review evidence, and confirms the preflight path does
not execute command nodes:

```bash
uv run python scripts/v09_command_review_contract_probe.py
```

This path uses only local deterministic graph validation: no API keys, no live
`agy`, no GitHub Actions billing, no provider calls, and no model billing.

## Local review bundles

Use the v0.10 local review bundle workflow when you need a saved
pre-execution evidence file for an operator-supplied local graph:

```bash
uv run agy-swarms preflight --graph tests/fixtures/local_runner/success-graph.json --review-bundle --output /tmp/agy-review-bundle.json
uv run python scripts/v10_review_bundle_probe.py
```

The saved JSON bundle validates against
`schemas/local-review-bundle-v1.schema.json` and includes references to
`schemas/local-graph-preflight-v1.schema.json` and
`schemas/local-command-review-v1.schema.json`. Bundle generation is read-only:
it does not execute command nodes, does not require `--allow-local-commands`,
does not require API keys, does not require live `agy`, and does not use
provider billing.

## Local review bundle inspection

Use the v0.11 local review bundle inspection workflow when you need to inspect
a saved bundle before granting local command execution:

```bash
uv run agy-swarms inspect --review-bundle /tmp/agy-review-bundle.json
uv run python scripts/v11_review_bundle_inspection_probe.py
```

The inspection command prints a compact JSON summary for the saved bundle
envelope, including the schema version, graph path, graph SHA-256 digest,
schema references, command-review coverage counts, review completeness, and
`commands_executed: false`. It reads only the saved bundle file: it does not
load or execute graph command nodes, does not require `--allow-local-commands`,
does not require API keys, does not require live `agy`, does not require
GitHub Actions, and does not use provider billing.

## Local review bundle diff

Use the v0.12 local review bundle diff workflow when you need to compare two
saved review bundles before approving a changed local graph:

```bash
uv run agy-swarms inspect --review-bundle-diff /tmp/agy-before-bundle.json /tmp/agy-after-bundle.json
uv run python scripts/v12_review_bundle_diff_probe.py
```

The diff command prints a stable JSON summary for saved bundle evidence,
including the before and after bundle paths, schema versions, graph SHA-256
digests, `graph_changed`, command node `command_changes`, review-complete
status for both bundles, schema references, and `commands_executed: false`.
It reads only the two saved bundle files: it does not load graph files, does
not execute graph command nodes, does not require `--allow-local-commands`,
does not require API keys, does not require live `agy`, does not require
hosted GitHub Actions, and does not use provider billing.

## Local review bundle run guard

Use the v0.13 local review bundle run guard when you need to bind a previously
reviewed bundle to the graph you are about to run. The guarded path remains
explicit: local command execution still requires `--allow-local-commands`, and
the saved review bundle is required only when the operator adds
`--require-review-bundle`.

```bash
uv run agy-swarms preflight --graph tests/fixtures/local_runner/success-graph.json --review-bundle --output /tmp/agy-review-bundle.json
uv run agy-swarms run --graph tests/fixtures/local_runner/success-graph.json --allow-local-commands --require-review-bundle /tmp/agy-review-bundle.json
uv run python scripts/v13_review_bundle_run_guard_probe.py
```

The guard validates the requested graph SHA-256 against the saved bundle,
checks that command-review evidence covers the local command surface, and stops
before command execution when the bundle is missing, malformed, unsupported,
mismatched, or incomplete. Rejected guard checks preserve the
`commands_executed: false` invariant and keep diagnostics redacted and
repairable. This workflow uses only local deterministic files and commands: no
API keys, no live `agy`, no GitHub Actions billing, no provider calls, and no
model billing.

## Guarded run provenance

Use the v0.14 guarded run provenance workflow when a saved local run report must
prove which review bundle authorized command execution:

```bash
uv run agy-swarms run --graph tests/fixtures/local_runner/success-graph.json \
  --allow-local-commands \
  --require-review-bundle /path/to/review-bundle.json \
  --report /path/to/guarded-report.json

uv run python scripts/v14_guarded_run_provenance_probe.py
```

Guarded reports include `review_bundle_guard` with `guarded_run: true`,
`graph_sha256_match: true`, command-review coverage lists, and
`commands_executed: false` for the guard validation step. Unguarded reports omit
the field. This workflow requires no API keys, no live `agy`, no hosted CI, and
no provider billing.

## Guarded report inspection

Use the v0.15 guarded report inspection workflow when you need read-only triage
for the review-bundle evidence saved by a guarded local run:

```bash
uv run python scripts/v15_guarded_report_inspection_probe.py
uv run agy-swarms inspect --checkpoint /tmp/agy-v14-guarded-report.json
uv run agy-swarms resume --checkpoint /tmp/agy-v14-guarded-report.json
```

`inspect --checkpoint` and saved-report `resume --checkpoint` surface the same
compact `summary.guarded_report` object when the saved report contains
`review_bundle_guard`. The summary records whether guard evidence exists,
whether the run was guarded, whether the graph digest matched, whether review
was complete, command-review mismatch counts, and `commands_executed: false`
for the guard validation step. The summary is triage evidence only: it avoids a
second copy of raw command argv values or the full review bundle evidence.

Saved-report `resume --checkpoint` reports `status: resume_loaded` and does not
rerun local command nodes. Unguarded saved reports keep the existing summary
shape and omit `summary.guarded_report`. This workflow uses only local
deterministic files and commands: no API keys, no live `agy`, no hosted CI, no
provider calls, and no model billing.

## Saved report summary contracts

Use the v0.16 saved report summary contract workflow when downstream tooling
needs machine-checkable JSON from read-only saved-report triage:

```bash
uv run python scripts/v16_saved_report_summary_contract_probe.py
```

The schema lives at `schemas/local-runner-summary-v1.schema.json` and covers
the `status` plus `summary` payload returned by `agy-swarms inspect
--checkpoint` and saved-report `agy-swarms resume --checkpoint`. Guarded saved
reports may include `summary.guarded_report`; unguarded saved reports omit it.
The guarded summary preserves the `commands_executed: false` invariant for the
guard validation step. This workflow uses no API keys, no live `agy`, no hosted
CI, no provider calls, and no model billing.

## Guarded report contract coverage

Use the v0.17 guarded report contract coverage workflow when downstream tooling
needs the full saved local-runner report, including guarded-run provenance, to
validate against the stable report schema:

```bash
uv run python scripts/v17_guarded_report_contract_probe.py
```

The probe creates a saved local review bundle, runs the success fixture through
the explicit `--require-review-bundle` guarded path, validates the guarded
saved report against `schemas/local-runner-report-v1.schema.json`, and confirms
ordinary unguarded reports still validate without `review_bundle_guard`.
Guarded reports must preserve `review_bundle_guard` evidence with
`guarded_run: true`, digest-match evidence, complete command-review coverage,
and `commands_executed: false` for the guard validation step.

The same probe also checks `inspect --checkpoint` and saved-report
`resume --checkpoint` expose matching `summary.guarded_report` triage evidence
without rerunning local command nodes. This workflow uses no API keys, no live
`agy`, no hosted CI, no provider calls, and no model billing.

## Guarded failure report contracts

v0.18 extends guarded full-report contract coverage to the tracked failing local
runner fixture. The probe builds a saved review bundle for
`tests/fixtures/local_runner/failure-graph.json`, runs the graph with
`--require-review-bundle`, writes a saved report, and validates that the failed
report still conforms to `schemas/local-runner-report-v1.schema.json`.

```bash
uv run python scripts/v18_guarded_failure_report_contract_probe.py
```

The expected evidence includes `status: failed`, non-empty failure metadata,
`review_bundle_guard`, `guarded_run: true`, and `commands_executed: false` for
the guard validation step. The probe also checks that read-only inspect/resume
summaries match and that saved-report resume does not rerun local command
nodes. The workflow requires no API keys, no live `agy`, no hosted CI, and no
provider billing.

## Guard rejection report contracts

v0.19 covers the pre-execution rejection path for guarded local runs. When
`agy-swarms run --graph ... --allow-local-commands --require-review-bundle ...
--report ...` rejects a stale, mismatched, incomplete, or malformed review
bundle before running command nodes, the CLI writes a separate
`status: rejected` report instead of a local-runner execution report.

```bash
uv run python scripts/v19_guard_rejection_report_contract_probe.py

uv run agy-swarms run --graph /path/to/changed-graph.json \
  --allow-local-commands \
  --require-review-bundle /path/to/stale-review-bundle.json \
  --report /path/to/guard-rejection-report.json
```

The schema lives at `schemas/local-runner-guard-rejection-v1.schema.json`.
Expected evidence includes `reason_class`, `review_bundle_guard`,
`graph_sha256_match`, `review_complete`, `missing_command_reviews`,
`mismatched_command_reviews`, and `commands_executed: false`. The run exits
non-zero, keeps stderr redacted but repairable, and writes only safe guard
diagnostics to the report. This workflow is billing-free and local by default:
no API keys, no live `agy`, no hosted CI, no provider calls, and no model
billing are required.

## Guard rejection report inspection

v0.20 makes saved guard rejection reports first-class read-only artifacts for
the normal operator triage commands:

```bash
uv run python scripts/v20_guard_rejection_inspection_probe.py

uv run agy-swarms inspect --checkpoint /path/to/guard-rejection-report.json
uv run agy-swarms resume --checkpoint /path/to/guard-rejection-report.json
```

`inspect --checkpoint` classifies the file as `kind: guard_rejection_report`.
Saved-report `resume --checkpoint` returns `status: resume_loaded` and
`source_status: rejected`. Both commands emit the same safe `summary` with
`reason_class`, `graph_sha256_match`, review completeness, missing and
mismatched command-review counts, and `commands_executed: false`. Neither
command loads the original graph for execution, reruns command nodes, or
requires `--allow-local-commands`.

The focused probe builds a stale review-bundle scenario with a marker-writing
command, confirms the guard rejection report is written, confirms the marker
does not run, and verifies inspect/resume summary parity. This workflow is
billing-free and local by default: no API keys, no live `agy`, no hosted CI, no
provider calls, and no model billing are required.

## Local runner report contracts

Use the v0.5 report contract gate when you need machine-checkable evidence for
saved local-runner JSON reports. The tracked schema lives at:

- `schemas/local-runner-report-v1.schema.json`

The focused contract probe replays the success, failure, and dependency-skip
fixtures into a temporary directory, validates each saved report against the
schema, checks the documented `inspect` / saved-report `resume` summary keys,
and confirms saved-report resume does not rerun local command nodes:

```bash
uv run python scripts/v05_report_contract_probe.py
```

To validate one report manually, create it outside the repository and inspect it
with the same billing-free CLI workflow:

```bash
uv run agy-swarms run --graph tests/fixtures/local_runner/success-graph.json --allow-local-commands --report /tmp/agy-v05-success-report.json
uv run agy-swarms inspect --checkpoint /tmp/agy-v05-success-report.json
uv run agy-swarms resume --checkpoint /tmp/agy-v05-success-report.json
```

The saved report should contain the stable top-level contract fields declared by
the schema: `status`, `states`, `blockers`, `spent_tokens`, `spent_usd`,
`concerns`, `changed_files`, and `results`.

This report-contract path uses only local deterministic commands: no API keys,
no live `agy`, no GitHub Actions billing, no provider calls, and no model
billing. Generated reports should stay in an operator-owned temporary path
unless a future milestone explicitly promotes a stable artifact.

## Local-live `agy` probes

The Phase 0 transport probes are not CI-safe. They exist to revalidate local provider behavior when needed:

- `scripts/phase0_s1_live_baseline.py`
- `scripts/phase0_s2_auth_probe.py`
- `scripts/phase0_s4_probe.py`
- `scripts/phase0_s6_model_diversity_probe.py`
- `scripts/phase0_g0_8_cost_latency_quality.py`

Run these only when intentionally rechecking live `agy` behavior. They may require:

- an installed `agy` CLI
- cached Google OAuth
- network access
- local timing/cost variance acceptance
- explicit review of generated evidence before committing it

## Updating tracked evidence

Exit probes default to non-writing mode. To refresh a tracked JSON evidence file under `.planning/spikes/`, run the individual probe with `--write`, inspect the diff, and commit only if the evidence change is intentional.
