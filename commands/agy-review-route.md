---
description: Resolve reviewer/closer adapter routing without execution
---

Test and resolve review routing configuration for reviewers and closers (e.g., using codex, off, or agy adapters).

Usage:
`/agy-review-route [--reviewer <adapter>] [--closer <adapter>]`

Instructions:
1. Parse reviewer and closer adapters from `$ARGUMENTS`.
2. Execute:
   ```bash
   uv run agy-swarms review-route $ARGUMENTS
   ```
3. Output the resolved routing results back to the user.
