"""Compression-first worker contract (FR-10/FR-11)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..types import ErrorClass, NodeSpec, ResultEnvelope

__all__ = [
    "WorkerArtifact",
    "WorkerContract",
    "WorkerContractError",
    "normalize_worker_output",
    "validate_worker_output",
]

_FORBIDDEN_FIELDS = frozenset(
    {
        "transcript",
        "messages",
        "raw_context",
        "full_context",
        "conversation",
        "chat_history",
    }
)


class WorkerContractError(Exception):
    """Raised when a worker output violates its scoped contract."""


@dataclass(frozen=True)
class WorkerContract:
    """Closed context handed to a worker."""

    node_id: str
    idempotency_key: str
    objective: str
    output_schema: dict[str, Any]
    tool_allowlist: list[str]
    boundaries: str
    prompt: str
    schema_version: int = 1

    @classmethod
    def from_node(cls, node: NodeSpec, *, prompt: str, schema_version: int = 1) -> WorkerContract:
        return cls(
            node_id=node.id,
            idempotency_key=node.idempotency_key,
            objective=node.objective,
            output_schema=dict(node.output_schema),
            tool_allowlist=list(node.tool_allowlist),
            boundaries=node.boundaries,
            prompt=prompt,
            schema_version=schema_version,
        )


@dataclass(frozen=True)
class WorkerArtifact:
    """Validated condensed worker output."""

    artifact: dict[str, Any]
    pointers: list[str]
    concerns: list[str] = field(default_factory=list)
    blockers: list[dict[str, str]] = field(default_factory=list)


def validate_worker_output(contract: WorkerContract, output: Mapping[str, Any]) -> WorkerArtifact:
    """Validate and return a compression-first worker artifact.

    The parent receives only a compact artifact and pointers. Transcript-like fields are
    rejected before the output can be normalized into a successful envelope.
    """
    if not isinstance(output, Mapping):
        raise WorkerContractError("worker output must be an object")
    artifact = output.get("artifact")
    if not isinstance(artifact, dict):
        raise WorkerContractError("worker output artifact must be an object")
    _reject_transcript_fields(artifact)
    _validate_schema(contract.output_schema, artifact)

    raw_pointers = output.get("pointers")
    if not isinstance(raw_pointers, list) or not raw_pointers:
        raise WorkerContractError("worker output must include at least one pointer")
    if not all(isinstance(pointer, str) and pointer for pointer in raw_pointers):
        raise WorkerContractError("worker output pointers must be non-empty strings")

    concerns = output.get("concerns", [])
    if not isinstance(concerns, list) or not all(isinstance(item, str) for item in concerns):
        raise WorkerContractError("worker output concerns must be strings")

    blockers = output.get("blockers", [])
    if not isinstance(blockers, list) or not all(isinstance(item, dict) for item in blockers):
        raise WorkerContractError("worker output blockers must be objects")

    return WorkerArtifact(
        artifact=dict(artifact),
        pointers=list(raw_pointers),
        concerns=list(concerns),
        blockers=[dict(item) for item in blockers],
    )


def normalize_worker_output(
    contract: WorkerContract,
    output: Mapping[str, Any],
    *,
    attempt: int = 0,
    adapter: str = "worker",
    model: str = "",
    thinking_level: str = "high",
    reservation_id: str | None = None,
) -> ResultEnvelope:
    """Normalize a worker output into the existing §D.2 result envelope."""
    try:
        worker_artifact = validate_worker_output(contract, output)
    except WorkerContractError as exc:
        return ResultEnvelope(
            node_id=contract.node_id,
            idempotency_key=contract.idempotency_key,
            status="failed",
            attempt=attempt,
            adapter=adapter,
            model=model,
            thinking_level=thinking_level,
            reservation_id=reservation_id,
            error_class=ErrorClass.SCHEMA_INVALID,
            blockers=[{"kind": "worker_contract", "detail": str(exc)}],
        )
    return ResultEnvelope(
        node_id=contract.node_id,
        idempotency_key=contract.idempotency_key,
        status="succeeded",
        attempt=attempt,
        adapter=adapter,
        model=model,
        thinking_level=thinking_level,
        reservation_id=reservation_id,
        artifact=worker_artifact.artifact,
        pointers=worker_artifact.pointers,
        concerns=worker_artifact.concerns,
        blockers=worker_artifact.blockers,
    )


def _reject_transcript_fields(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key in _FORBIDDEN_FIELDS:
                raise WorkerContractError(f"forbidden transcript field: {key}")
            _reject_transcript_fields(nested)
    elif isinstance(value, list):
        for item in value:
            _reject_transcript_fields(item)


def _validate_schema(schema: Mapping[str, Any], artifact: Mapping[str, Any]) -> None:
    if not schema:
        return
    if schema.get("type", "object") != "object":
        raise WorkerContractError("output schema root must be object")
    for field_name in schema.get("required", []):
        if field_name not in artifact:
            raise WorkerContractError(f"artifact missing required field: {field_name}")

    properties = schema.get("properties", {})
    if schema.get("additionalProperties", True) is False:
        unexpected = sorted(set(artifact) - set(properties))
        if unexpected:
            raise WorkerContractError(f"artifact has unexpected field: {unexpected[0]}")

    for field_name, spec in properties.items():
        if field_name in artifact and not _matches_type(artifact[field_name], spec.get("type")):
            raise WorkerContractError(f"artifact field {field_name!r} must be {spec.get('type')}")


def _matches_type(value: Any, expected: str | None) -> bool:
    if expected is None:
        return True
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "null":
        return value is None
    raise WorkerContractError(f"unsupported schema type: {expected}")
