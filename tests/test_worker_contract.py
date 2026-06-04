from __future__ import annotations

from agy_swarms.types import ErrorClass, NodeSpec
from agy_swarms.workers.contract import (
    WorkerContract,
    WorkerContractError,
    normalize_worker_output,
    validate_worker_output,
)


def _node() -> NodeSpec:
    return NodeSpec(
        id="worker-a",
        role="worker",
        objective="Review the scoped planning excerpt.",
        output_schema={
            "type": "object",
            "required": ["summary", "data"],
            "properties": {
                "summary": {"type": "string"},
                "data": {"type": "object"},
            },
            "additionalProperties": True,
        },
        tool_allowlist=["read"],
        boundaries="Use only the scoped packet.",
        idempotency_key="key-a",
    )


def test_worker_contract_from_node_preserves_scope_fields():
    contract = WorkerContract.from_node(_node(), prompt="rendered prompt")

    assert contract.node_id == "worker-a"
    assert contract.idempotency_key == "key-a"
    assert contract.objective == "Review the scoped planning excerpt."
    assert contract.output_schema["required"] == ["summary", "data"]
    assert contract.tool_allowlist == ["read"]
    assert contract.boundaries == "Use only the scoped packet."
    assert contract.prompt == "rendered prompt"


def test_validate_worker_output_accepts_dense_artifact_with_pointers():
    contract = WorkerContract.from_node(_node(), prompt="prompt")
    output = {
        "artifact": {
            "summary": "The scoped excerpt has one actionable contradiction.",
            "data": {"contradictions": 1},
        },
        "pointers": ["phase0-results.md#G0.8"],
        "concerns": ["needs owner signoff"],
    }

    artifact = validate_worker_output(contract, output)

    assert artifact.artifact == output["artifact"]
    assert artifact.pointers == ["phase0-results.md#G0.8"]
    assert artifact.concerns == ["needs owner signoff"]


def test_normalize_worker_output_returns_succeeded_result_envelope():
    contract = WorkerContract.from_node(_node(), prompt="prompt")
    envelope = normalize_worker_output(
        contract,
        {
            "artifact": {"summary": "dense", "data": {"ok": True}},
            "pointers": ["artifact://one"],
        },
        attempt=2,
        adapter="worker-contract-test",
        reservation_id="r1",
    )

    assert envelope.status == "succeeded"
    assert envelope.node_id == "worker-a"
    assert envelope.idempotency_key == "key-a"
    assert envelope.attempt == 2
    assert envelope.adapter == "worker-contract-test"
    assert envelope.reservation_id == "r1"
    assert envelope.artifact == {"summary": "dense", "data": {"ok": True}}
    assert envelope.pointers == ["artifact://one"]


def test_normalize_worker_output_rejects_transcript_dump_as_schema_invalid():
    contract = WorkerContract.from_node(_node(), prompt="prompt")
    envelope = normalize_worker_output(
        contract,
        {
            "artifact": {
                "summary": "dense",
                "data": {"ok": True},
                "transcript": [{"role": "assistant", "content": "full chat"}],
            },
            "pointers": ["artifact://one"],
        },
    )

    assert envelope.status == "failed"
    assert envelope.error_class is ErrorClass.SCHEMA_INVALID
    assert envelope.blockers == [
        {"kind": "worker_contract", "detail": "forbidden transcript field: transcript"}
    ]


def test_validate_worker_output_requires_pointers():
    contract = WorkerContract.from_node(_node(), prompt="prompt")

    try:
        validate_worker_output(contract, {"artifact": {"summary": "dense", "data": {}}})
    except WorkerContractError as exc:
        assert str(exc) == "worker output must include at least one pointer"
    else:  # pragma: no cover - keeps failure message explicit.
        raise AssertionError("expected WorkerContractError")


def test_validate_worker_output_applies_declared_output_schema():
    contract = WorkerContract.from_node(_node(), prompt="prompt")

    try:
        validate_worker_output(
            contract,
            {"artifact": {"summary": "dense"}, "pointers": ["artifact://one"]},
        )
    except WorkerContractError as exc:
        assert str(exc) == "artifact missing required field: data"
    else:  # pragma: no cover - keeps failure message explicit.
        raise AssertionError("expected WorkerContractError")
