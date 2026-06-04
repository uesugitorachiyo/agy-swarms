---
description: Resume execution from an existing checkpoints directory
---

Resume an interrupted or failed task execution from the last saved checkpoints folder or file.

Usage:
`/agy-resume <path-to-checkpoint>`

Instructions:
1. Ensure the checkpoint path is provided in `$ARGUMENTS`.
2. Resume execution:
   ```bash
   uv run agy-swarms resume --checkpoint $ARGUMENTS
   ```
3. Output progress and final results of the resumed execution.
