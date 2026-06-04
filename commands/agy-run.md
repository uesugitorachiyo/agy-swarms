---
description: Run the parallel swarm conductor for a task spec or graph
---

Decompose, schedule, and execute a task specification or a pre-decomposed graph JSON file.

Usage:
`/agy-run <path-to-file> [--allow-local-commands] [--reviewer <adapter>] [--closer <adapter>] [other flags]`

Instructions:
1. Extract the file path and any flags from `$ARGUMENTS`.
2. If the target file is a task specification, run with `--task`:
   ```bash
   uv run agy-swarms run --task <path-to-file> [flags]
   ```
   If the target file is a decomposed graph, run with `--graph`:
   ```bash
   uv run agy-swarms run --graph <path-to-file> [flags]
   ```
3. Critical Security: If local execution is requested, require the `--allow-local-commands` flag. Review any commands or plans before running, and ensure the user explicitly approves.
