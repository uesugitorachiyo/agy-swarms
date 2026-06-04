---
name: agy-swarms
description: Use when planning, preflighting, running, inspecting, or resuming local typed task-graph workflows with agy-swarms.
---

# agy-swarms Skill

Use this skill when a task benefits from a deterministic local task graph:
preflight first, review command surfaces, then run only when local command
execution is explicitly allowed.

## Core Commands

Run commands from the repository root.

Preflight a graph without executing commands:

```bash
uv run agy-swarms preflight --graph tests/fixtures/local_runner/success-graph.json
```

Create a saved review bundle before execution:

```bash
uv run agy-swarms preflight \
  --graph tests/fixtures/local_runner/success-graph.json \
  --review-bundle \
  --output /tmp/agy-review-bundle.json
```

Run a graph and write a saved report:

```bash
uv run agy-swarms run \
  --graph tests/fixtures/local_runner/success-graph.json \
  --allow-local-commands \
  --report /tmp/agy-swarms-success-report.json
```

Inspect a saved report:

```bash
uv run agy-swarms inspect --checkpoint /tmp/agy-swarms-success-report.json
```

Load a saved report through the resume path without rerunning local command
nodes:

```bash
uv run agy-swarms resume --checkpoint /tmp/agy-swarms-success-report.json
```

## Operating Rules

- Prefer `preflight` before `run`.
- Treat local command execution as a side effect.
- Use `--allow-local-commands` only when the command surface has been reviewed.
- Store generated reports and review bundles outside the repository unless a
  fixture is intentionally being added.
- Keep worker output concise: return summaries, evidence, and file pointers
  rather than raw transcripts.
