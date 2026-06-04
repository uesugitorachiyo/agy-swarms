---
name: agy-swarms
description: "Decompose, orchestrate, and execute complex coding and analysis tasks using parallel Gemini 3.5 Flash worker swarms."
---

# agy-swarms Skill

Use this skill when you need to schedule, manage, or debug concurrent multi-agent executions using the `agy-swarms` library and CLI conductor.

## Command Wrappers & Slash Shortcuts

This plugin provides explicit command wrappers to simplify agent invocation and reduce ambiguity. Use the following slash commands instead of manual CLI execution:

*   **/agy-preflight `<graph-path>`**: Validate and summarize a local graph without executing command nodes.
*   **/agy-run `<task-or-graph-path>`**: Run the task graph conductor. If local execution is requested, require reviewer checks and `--allow-local-commands`.
*   **/agy-inspect `<args>`**: Inspect details of checkpoints (`--checkpoint <path>`) or review bundles (`--review-bundle <path>`).
*   **/agy-resume `<checkpoint-path>`**: Resume a failed or interrupted conductor run from checkpoints.
*   **/agy-review-route `<args>`**: Test reviewer/closer adapter routing (e.g. `codex`, `off`, `agy`) without run execution.

## Raw CLI Core Commands

If you need to run commands manually, all commands are run using `uv` from the repository root:

*   **Plan and Preview Graph:** Validate task shape and check the decomposition plan before running:
    ```bash
    uv run agy-swarms plan --task <path-to-task.json>
    ```
*   **Run Conductor:** Run the task graph through the parallel conductor:
    ```bash
    uv run agy-swarms run --task <path-to-task.json> --allow-local-commands
    ```
*   **Resume Execution:** If a run fails or is interrupted, resume from the last saved checkpoints folder:
    ```bash
    uv run agy-swarms resume --checkpoint <path-to-checkpoints-dir>
    ```
*   **Inspect Results:** Inspect structured result logs and tokens:
    ```bash
    uv run agy-swarms inspect --checkpoint <path-to-checkpoint>
    ```


## Task Specification Shape

A task spec file is a simple JSON file specifying the high-level objective:

```json
{
  "task": "Decompose and execute the migration of database models to v2",
  "model_pins": {
    "default": "gemini-3.5-flash"
  }
}
```

## Best Practices
1. **Parallel Execution:** Use `agy-swarms` when tasks can be decoupled and executed in parallel (e.g. running tests, building separate files).
2. **Context Compression:** Keep task outputs concise; workers return summarized evidence and file pointers rather than dumping raw transcripts.
3. **Command Safety:** Always review plans using `plan` first. Local node execution requires the `--allow-local-commands` flag.
