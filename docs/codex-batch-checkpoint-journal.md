# Codex Batch Checkpoint Journal

Codex reviewer/closer batching is intentionally disabled when checkpointing is active until the batch invocation can be represented as a replayable journal entry. A checkpointed batch must preserve the same per-node idempotency guarantees as single-node execution.

## Journal Entry

Each Codex batch invocation should write one batch journal record before dispatch:

- `batch_id`: deterministic hash of epoch id, ordered node ids, and ordered idempotency keys.
- `epoch_id` and `epoch_seq`: the checkpoint epoch that owns the batch.
- `node_ids`: ordered member node ids.
- `idempotency_keys`: ordered member node keys.
- `reservation_ids`: per-node reservation ids created before dispatch.
- `adapter`: `codex`.
- `model` and `reasoning_effort`: resolved once for the batch.
- `status`: `reserved`, `running`, `committed`, or `failed`.
- `started_at` and `ended_at`: batch-level wall-clock timestamps.

The journal must not contain prompt text, source code, command argv, or objective expansions beyond existing node ids and metadata.

## Commit Barrier

A batch has one external Codex invocation but multiple node envelopes. Checkpoint commit must use a barrier:

1. Reserve every member node and persist the `reserved` journal entry.
2. Mark the journal `running` before invoking Codex.
3. Parse and validate one envelope per node.
4. Commit all node envelopes and state transitions in one checkpoint transaction.
5. Mark the journal `committed` only after every node commit succeeds.

If any node envelope is missing or schema-invalid, the batch should produce deterministic per-node failure envelopes and commit them through the same barrier. Partial success inside one checkpointed batch is not replay-safe unless the checkpoint transaction can prove exactly which node commits landed.

## Replay Rules

On resume:

- `committed`: use the per-node checkpoint envelopes; do not invoke Codex again.
- `reserved` or `running` with no committed envelopes: release stale reservations and retry the batch or fall back to single-node dispatch.
- `failed`: do not replay unless the failure class is transient and retry policy allows it.
- mixed per-node state without `committed`: treat as checkpoint corruption and require operator inspection.

## Failure Handling

Transport failure produces one failure envelope per member node with the same transport diagnostic. Schema failure also produces one failure envelope per member node unless the parser can prove only a specific node response was malformed. Token accounting should copy the batch output token count to each envelope until the telemetry schema supports batch-level amortization.

## Enablement Criteria

Checkpointed Codex batching should remain disabled until tests cover:

- resume from `reserved`;
- resume from `running`;
- resume from `committed`;
- schema-invalid batch output;
- one missing node response;
- stale reservation cleanup;
- no prompt/code leakage into the journal.
