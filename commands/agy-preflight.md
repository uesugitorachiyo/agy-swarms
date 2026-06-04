---
description: Validate and summarize a local graph without execution
---

Run a preflight validation check on a `TaskGraph` JSON file before scheduling/running it.

Usage:
`/agy-preflight <path-to-graph.json> [options]`

Instructions:
1. Ensure that the graph path is provided in `$ARGUMENTS`.
2. Execute the following command in the workspace root:
   ```bash
   uv run agy-swarms preflight --graph $ARGUMENTS
   ```
3. Do NOT execute any actual command nodes or grant local command permissions.
4. Report the resulting preflight check output and node summary.
