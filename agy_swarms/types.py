"""§D.1–§D.7 — the normative typed shapes the engine is built from.

This module owns the static/runtime split that makes resume correct (§D.1):
``NodeSpec`` is static and hashed into ``idempotency_key``; ``NodeRuntimeState`` is
mutable and engine-owned (never hashed). The ``Epoch`` split (§D.6) keeps two distinct
fields — ``epoch_id`` (content hash → cache validity, FR-7) and ``epoch_seq`` (monotonic
counter → ledger key + orphan sweep, §D.4/FR-30) — that SHALL NOT be conflated.

``compute_idempotency_key`` implements the precise §D.1 enumeration: ``id``, ``outputs``
and ``timeout_s`` are deliberately NOT hashed; ``inputs`` / ``output_schema`` / tools are
folded in as §D.0 digests (resolved at the pending→ready transition, §D.1 [H4]).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .canonical import (
    canonical,
    output_schema_digest,
    resolved_input_digest,
    sha256_hex,
    tool_schema_impl_digest,
)

__all__ = [
    "NodeStatus",
    "FailureClass",
    "RunStatus",
    "ErrorClass",
    "Caps",
    "RetryPolicy",
    "Reducer",
    "MapSpec",
    "ToolEntry",
    "NodeSpec",
    "compute_idempotency_key",
    "NodeRuntimeState",
    "TaskGraph",
    "TaskSpec",
    "Epoch",
    "compute_epoch_id",
    "EpochBump",
    "SectionConflict",
    "DriftRecord",
    "BlobRef",
    "ResultEnvelope",
]


# --- closed enums (§D.1/§D.2/§D.7) -----------------------------------------


class NodeStatus(StrEnum):
    """The 8-member node lifecycle (§D.1 state machine)."""

    PENDING = "pending"
    READY = "ready"
    RESERVED = "reserved"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class FailureClass(StrEnum):
    """Retry verdict (§D.2) — distinct axis from ``ErrorClass`` (the diagnostic cause)."""

    TRANSIENT = "Transient"
    DETERMINISTIC = "Deterministic"
    BUDGET = "Budget"


class RunStatus(StrEnum):
    """Run-level closed enum (§D.7). Strict subset of NodeStatus."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorClass(StrEnum):
    """8-member diagnostic cause carried by the envelope + runtime mirror (§D.2/§D.1)."""

    NONE = "none"
    SCHEMA_INVALID = "schema_invalid"
    TRANSPORT = "transport"
    AUTH = "auth"
    TIMEOUT = "timeout"
    BUDGET = "budget"
    TOOL = "tool"
    UNKNOWN = "unknown"


# --- NodeSpec sub-structures (§D.1) ----------------------------------------


@dataclass(frozen=True)
class Caps:
    """Per-node hard ceilings feeding ``est()`` (§D.1/§D.4)."""

    max_output_tokens: int = 0
    max_thinking_tokens: int = 0
    max_tool_calls: int = 0


@dataclass(frozen=True)
class RetryPolicy:
    """Per-node retry narrowing (§D.1)."""

    max_schema_retries: int = 0
    retryable_error_classes: tuple[str, ...] = ("transport", "timeout")


@dataclass(frozen=True)
class Reducer:
    """The ONE reducer-binding field (§D.1) — the whole object is the hashed unit."""

    kind: str  # concat|json_merge|custom
    custom_id: str | None = None


@dataclass(frozen=True)
class MapSpec:
    """Dynamic fan-out descriptor (§D.1.2)."""

    collection_input: str
    element_artifact: str
    max_fanout: int
    child_template: str
    weights: tuple[int, ...] | None = None


@dataclass(frozen=True)
class ToolEntry:
    """Registry entry (agy.lock ``[tools]``, §D.5) — schema + impl source hash."""

    schema: dict[str, Any]
    impl_source_sha256: str


# --- NodeSpec (static; hashed) ---------------------------------------------


@dataclass
class NodeSpec:
    """Static, planner-authored node contract hashed into ``idempotency_key`` (§D.1)."""

    id: str
    role: str
    objective: str
    kind: str = "single"
    prompt_template: str = ""
    map: MapSpec | None = None
    inputs: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    reducer: Reducer | None = None
    output_schema: dict[str, Any] = field(default_factory=dict)
    tool_allowlist: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    transport: str = "scripted"
    model_tier: str = "flash_high"
    boundaries: str = ""
    command: list[str] | None = None
    revision: int = 0
    max_turns: int = 0
    caps: Caps = field(default_factory=Caps)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    timeout_s: int = 0
    idempotency_key: str = ""


def compute_idempotency_key(
    spec: NodeSpec,
    resolved_inputs: Mapping[str, Any] | None = None,
    tool_registry: Mapping[str, ToolEntry] | None = None,
) -> str:
    """Derive ``idempotency_key = sha256_hex(canonical(<hashed §D.1 fields>))``.

    The hashed set is the precise §D.1 enumeration. ``inputs`` are folded in as
    resolved-value digests (raising ``KeyError`` if an input is unresolved — the
    ready-time rule, §D.1 [H4]); ``output_schema`` and each tool fold in as §D.0
    sub-digests; ``id``/``outputs``/``timeout_s``/``idempotency_key`` are excluded.
    """
    resolved = resolved_inputs or {}
    registry = tool_registry or {}

    payload: dict[str, Any] = {
        "objective": spec.objective,
        "prompt_template": spec.prompt_template,
        "kind": spec.kind,
        "dependencies": list(spec.dependencies),
        "tool_allowlist": list(spec.tool_allowlist),
        "required_capabilities": list(spec.required_capabilities),
        "transport": spec.transport,
        "model_tier": spec.model_tier,
        "boundaries": spec.boundaries,
        "revision": spec.revision,
        "max_turns": spec.max_turns,
        "caps": asdict(spec.caps),
        "retry_policy": asdict(spec.retry_policy),
        "output_schema_digest": output_schema_digest(spec.output_schema),
        "input_digests": [resolved_input_digest(resolved[i]) for i in spec.inputs],
        "tool_digests": [
            tool_schema_impl_digest(registry[t].schema, registry[t].impl_source_sha256)
            for t in spec.tool_allowlist
        ],
    }
    if spec.map is not None:
        payload["map"] = asdict(spec.map)
    if spec.reducer is not None:
        payload["reducer"] = asdict(spec.reducer)
    if spec.command is not None:
        payload["command"] = list(spec.command)
    return sha256_hex(canonical(payload))


# --- NodeRuntimeState (mutable; never hashed) ------------------------------


@dataclass
class NodeRuntimeState:
    """Engine-owned mutable per-node state (§D.1). Checkpointed; monotonic across resume."""

    node_id: str
    status: NodeStatus = NodeStatus.PENDING
    attempt: int = 0
    remaining_schema_retries: int = 0
    budget_consumed: dict[str, Any] = field(default_factory=lambda: {"tokens": 0, "usd": 0.0})
    reservation_id: str | None = None
    depth: int = 0
    priority: int = 0
    result_ref: str | None = None
    error_class: ErrorClass = ErrorClass.NONE


# --- graph + epoch ---------------------------------------------------------


@dataclass
class TaskGraph:
    """``{ nodes, edges, seed }`` (§D.1)."""

    nodes: list[NodeSpec] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)
    seed: int = 0


@dataclass
class TaskSpec:
    """Top-level run-intake request (ROADMAP Phase 1; FR-1).

    ``model_pins`` is a REQUIRED field (AC-27/NFR-7): a run whose ``TaskSpec`` omits
    model-version pins SHALL be rejected at intake with a specific error before any
    worker dispatches (enforced by ``validate.validate_intake``). A run submits either a
    raw ``task`` (decomposed by a planner node, AC-0.5) or a pre-built ``graph``.
    """

    task: str = ""
    graph: TaskGraph | None = None
    model_pins: dict[str, str] = field(default_factory=dict)
    context_hash: str = ""
    allow_drift: bool = False


@dataclass(frozen=True)
class Epoch:
    """Two distinct fields (§D.6): ``epoch_seq`` (ordering) and ``epoch_id`` (identity)."""

    epoch_seq: int
    epoch_id: str


def compute_epoch_id(agy_lock_hash: str, engine_sha: str, prompt_pack_version: str) -> str:
    """``epoch_id`` = content hash of the three identity inputs (§D.6).

    A revert reproducing prior content reproduces the prior ``epoch_id`` (cache re-hit),
    while ``epoch_seq`` still advances monotonically (the reason the two fields exist).
    """
    return sha256_hex(canonical([agy_lock_hash, engine_sha, prompt_pack_version]))


@dataclass
class EpochBump:
    """FR-32 bump record (§D.6): new epoch + the closed allowlist it authorizes."""

    new_epoch: Epoch
    sections: list[str] = field(default_factory=list)


@dataclass
class SectionConflict:
    """FR-31 conflict (§D.6)."""

    section: str
    epoch: str
    existing_writer_node: str
    attempted_writer_node: str
    reason: str  # different-writer | committed-value-exists | not-authorized-by-epoch-bump


@dataclass(frozen=True)
class DriftRecord:
    """§D.5 per-key lockfile drift, recorded in the run record (§D.7).

    ``category`` is one of ``model_pins`` / ``prompt_hashes`` / ``tool_versions``;
    ``expected`` is the locked (agy.lock) value, ``actual`` the resolved-at-execute-time
    value. ``model_pins``/``prompt_hashes`` drift is control-flow-affecting (aborts without
    ``--allow-drift``); ``tool_versions`` drift is warn-only (AC-31, SPEC:492).
    """

    category: str  # model_pins | prompt_hashes | tool_versions
    key: str
    expected: str
    actual: str


# --- worker result envelope (§D.2) -----------------------------------------


@dataclass(frozen=True)
class BlobRef:
    """Content-addressed blob pointer (§D.2)."""

    sha256: str
    len_bytes: int
    mime: str


@dataclass
class ResultEnvelope:
    """Normalized adapter output carrying provenance + lifecycle (§D.2).

    ``artifact`` is the schema-validated payload inside it. ``failure_class`` SHALL be
    non-null iff ``status != succeeded`` (the fail-closed rule lives in the conductor).
    """

    node_id: str
    idempotency_key: str
    status: str  # succeeded|failed|cancelled|timed_out
    attempt: int = 0
    adapter: str = "scripted"
    model: str = ""
    thinking_level: str = "high"
    reservation_id: str | None = None
    started_at: str = ""
    ended_at: str = ""
    error_class: ErrorClass = ErrorClass.NONE
    failure_class: FailureClass | None = None
    retryable: bool = False
    artifact: dict[str, Any] = field(default_factory=dict)
    pointers: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    stdout_ref: str | None = None
    diff_ref: str | None = None
    concerns: list[str] = field(default_factory=list)
    blockers: list[dict[str, str]] = field(default_factory=list)
    token_usage: dict[str, Any] = field(
        default_factory=lambda: {
            "input": 0,
            "thinking": 0,
            "output": 0,
            "cached": 0,
            "accounting": "exact",
        }
    )
    cost_usd: float = 0.0
