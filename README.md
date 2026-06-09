# agy-swarms

`agy-swarms` is a local typed task-graph runner for agentic workflows.

It gives you deterministic scheduling, budget accounting, policy gates,
checkpointed evidence, saved reports, preflight review bundles, and resumable
inspection for local graph execution.

The project is designed for operators who want to run parallel agent-shaped
workflows without making the runtime itself an opaque agent. Models and CLIs can
sit behind adapters; graph validation, scheduling, command review, reporting,
and replayable evidence stay in code.

## What It Does

- Loads task graphs from JSON.
- Validates nodes, dependencies, budgets, and command surfaces before execution.
- Runs deterministic local command nodes only when explicitly allowed.
- Emits saved JSON reports for inspection and resume flows.
- Produces command-review and review-bundle evidence before a guarded run.
- Provides adapters for scripted execution and review routing experiments.

## Install

Use `uv` from a fresh checkout:

```bash
uv sync --extra dev --extra gemini
```

Run the test suite:

```bash
uv run python -m pytest -q
```

Run the CLI:

```bash
uv run agy-swarms --help
```

## Quickstart

Preflight a tracked local-runner graph without executing commands:

```bash
uv run agy-swarms preflight --graph tests/fixtures/local_runner/success-graph.json
```

Run the same graph and write a saved report:

```bash
uv run agy-swarms run \
  --graph tests/fixtures/local_runner/success-graph.json \
  --allow-local-commands \
  --report /tmp/agy-swarms-success-report.json
```

Inspect the saved report:

```bash
uv run agy-swarms inspect --checkpoint /tmp/agy-swarms-success-report.json
```

Load the saved report through the resume path without rerunning local command
nodes:

```bash
uv run agy-swarms resume --checkpoint /tmp/agy-swarms-success-report.json
```

## Release Checks

The public CI path is intentionally local and deterministic:

```bash
uv run ruff check .
uv run ruff format --check .
uv run python -m pytest -q
uv build
```

For hosted macOS/Windows/Linux verification, run the manual GitHub Actions `CI`
workflow. It uses a `workflow_dispatch` matrix across `ubuntu-latest`,
`macos-latest`, and `windows-latest`.

Additional release verification notes live in
[docs/release-verification.md](docs/release-verification.md). Version policy
notes live in [docs/versioning.md](docs/versioning.md). Architecture boundaries
are summarized in [docs/architecture.md](docs/architecture.md).

## Safety Model

`agy-swarms` treats command execution as an explicit side effect. The graph
preflight and review-bundle flows are read-only. Local command nodes require
the `--allow-local-commands` flag, and guarded runs can require a saved review
bundle before command execution proceeds.

Provider API keys are not required for the deterministic local-runner path.

## Antigravity Plugin

The repository includes `plugin.json` and `skills/agy-swarms/SKILL.md` for
Antigravity-compatible plugin installation.

After cloning, install the local checkout:

```bash
git clone https://github.com/uesugitorachiyo/agy-swarms.git
cd agy-swarms
agy plugin install .
```

`agy` 1.0.5 does not currently install this plugin directly from a raw GitHub
URL such as `agy plugin install https://github.com/uesugitorachiyo/agy-swarms`.
Use the fresh-clone command above, then install the local checkout.

To remove it:

```bash
agy plugin uninstall agy-swarms
```

## License

`agy-swarms` is licensed under either of:

- Apache License, Version 2.0 ([LICENSE-APACHE](LICENSE-APACHE))
- MIT License ([LICENSE-MIT](LICENSE-MIT))

Choose whichever license fits your use case.
