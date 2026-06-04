---
description: Inspect a checkpoint, report, or saved review bundle
---

Inspect the details, status, blockers, and changes in a checkpoints folder, a local runner report, or a saved review bundle.

Usage:
`/agy-inspect --checkpoint <path-to-checkpoint>`
`/agy-inspect --review-bundle <path-to-review-bundle.json>`

Instructions:
1. Extract the target argument and option from `$ARGUMENTS`.
2. Execute the inspection command:
   ```bash
   uv run agy-swarms inspect $ARGUMENTS
   ```
3. Report the parsed status counts, blocker/concern counts, and list of changed files to the user.
