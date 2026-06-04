"""D4.0 code-owned ground-truth verification gates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ..gates import Verdict

__all__ = [
    "GroundTruthSignal",
    "Revision",
    "VerifyLoopReport",
    "VerifyLoopStatus",
    "VerifyLoopStep",
    "VerifyResult",
    "VerifyStatus",
    "ground_truth_verify_gate",
    "run_evaluator_optimizer_loop",
    "verify_output",
]


class VerifyStatus(StrEnum):
    """Code-owned verification outcome."""

    PASSED = "passed"
    FAILED = "failed"


class VerifyLoopStatus(StrEnum):
    """Bounded evaluator-optimizer loop termination status."""

    PASSED = "passed"
    MAX_REVISIONS = "max_revisions"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NON_MONOTONIC = "non_monotonic"


@dataclass(frozen=True)
class GroundTruthSignal:
    """Declared test/lint/compile/schema signal consumed by a verify gate."""

    id: str
    kind: str
    artifact_pointer: str
    passed: bool
    message: str = ""


@dataclass(frozen=True)
class VerifyResult:
    """Deterministic verification result over declared ground-truth signals."""

    status: VerifyStatus
    defects: tuple[str, ...] = ()
    defect_ids: tuple[str, ...] = ()
    signal_count: int = 0


@dataclass(frozen=True)
class Revision:
    """Generator revision claiming to address named verifier defects."""

    id: str
    addressed_defect_ids: tuple[str, ...]
    cost_tokens: int = 0


@dataclass(frozen=True)
class VerifyLoopStep:
    """One monotonic evaluator-optimizer loop step."""

    revision_id: str
    unresolved_defect_ids: tuple[str, ...]
    addressed_defect_ids: tuple[str, ...]
    spent_tokens: int


@dataclass(frozen=True)
class VerifyLoopReport:
    """FR-21/FR-22 bounded evaluator-optimizer loop report."""

    status: VerifyLoopStatus
    terminated: bool
    revisions: int
    unresolved_defect_ids: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    steps: tuple[VerifyLoopStep, ...] = ()
    generator_node_id: str = ""
    verifier_node_id: str = ""


_GROUND_TRUTH_KINDS = ("compile", "lint", "schema", "test")


def verify_output(output: dict[str, Any], contract: dict[str, Any]) -> VerifyResult:
    """Return a deterministic verification result without consulting an LLM."""
    signals = tuple(_coerce_signal(item) for item in contract.get("signals", ()))
    defects: list[str] = []
    defect_ids: list[str] = []
    for signal in sorted(signals, key=lambda item: (item.kind, item.id)):
        if signal.kind not in _GROUND_TRUTH_KINDS:
            defect_ids.append(f"invalid-signal:{signal.id}")
            defects.append(f"invalid-signal:{signal.id}: unknown kind {signal.kind}")
            continue
        if signal.passed:
            continue
        defect_id = f"{signal.kind}:{signal.id}"
        defect_ids.append(defect_id)
        detail = f"{defect_id}: {signal.artifact_pointer} failed"
        if signal.message:
            detail += f": {signal.message}"
        defects.append(detail)
    return VerifyResult(
        status=VerifyStatus.PASSED if not defects else VerifyStatus.FAILED,
        defects=tuple(defects),
        defect_ids=tuple(defect_ids),
        signal_count=len(signals),
    )


def ground_truth_verify_gate(output: dict[str, Any], contract: dict[str, Any]) -> Verdict:
    """Gate adapter for ``run_gate`` / FR-33 double-execution."""
    result = verify_output(output, contract)
    return Verdict(passed=result.status == VerifyStatus.PASSED, defects=result.defects)


def run_evaluator_optimizer_loop(
    initial_defect_ids: tuple[str, ...],
    revisions: tuple[Revision, ...],
    *,
    max_revisions: int,
    budget_tokens: int,
    generator_node_id: str,
    verifier_node_id: str,
) -> VerifyLoopReport:
    """Run a bounded verify-repair loop over named defects.

    The generator may only make progress by removing verifier-named defect ids.
    Stale or unrelated revisions are rejected before they can consume a retry.
    """
    if generator_node_id == verifier_node_id:
        raise ValueError("generator and verifier contexts must be separate")
    if max_revisions < 0:
        raise ValueError("max_revisions must be non-negative")
    if budget_tokens < 0:
        raise ValueError("budget_tokens must be non-negative")

    unresolved = _stable_unique(initial_defect_ids)
    if not unresolved:
        return VerifyLoopReport(
            status=VerifyLoopStatus.PASSED,
            terminated=True,
            revisions=0,
            unresolved_defect_ids=(),
            generator_node_id=generator_node_id,
            verifier_node_id=verifier_node_id,
        )

    spent_tokens = 0
    steps: list[VerifyLoopStep] = []
    for revision in revisions[:max_revisions]:
        if revision.cost_tokens < 0:
            raise ValueError("revision cost_tokens must be non-negative")
        if spent_tokens + revision.cost_tokens > budget_tokens:
            return VerifyLoopReport(
                status=VerifyLoopStatus.BUDGET_EXHAUSTED,
                terminated=True,
                revisions=len(steps),
                unresolved_defect_ids=unresolved,
                blockers=(f"budget exhausted before {revision.id}",),
                steps=tuple(steps),
                generator_node_id=generator_node_id,
                verifier_node_id=verifier_node_id,
            )

        addressed = tuple(item for item in revision.addressed_defect_ids if item in unresolved)
        if not addressed:
            return VerifyLoopReport(
                status=VerifyLoopStatus.NON_MONOTONIC,
                terminated=True,
                revisions=len(steps),
                unresolved_defect_ids=unresolved,
                blockers=(f"revision {revision.id} did not reduce unresolved defects",),
                steps=tuple(steps),
                generator_node_id=generator_node_id,
                verifier_node_id=verifier_node_id,
            )

        spent_tokens += revision.cost_tokens
        unresolved = tuple(item for item in unresolved if item not in addressed)
        steps.append(
            VerifyLoopStep(
                revision_id=revision.id,
                unresolved_defect_ids=unresolved,
                addressed_defect_ids=addressed,
                spent_tokens=spent_tokens,
            )
        )
        if not unresolved:
            return VerifyLoopReport(
                status=VerifyLoopStatus.PASSED,
                terminated=True,
                revisions=len(steps),
                unresolved_defect_ids=(),
                steps=tuple(steps),
                generator_node_id=generator_node_id,
                verifier_node_id=verifier_node_id,
            )

    return VerifyLoopReport(
        status=VerifyLoopStatus.MAX_REVISIONS,
        terminated=True,
        revisions=len(steps),
        unresolved_defect_ids=unresolved,
        blockers=("max revisions reached",),
        steps=tuple(steps),
        generator_node_id=generator_node_id,
        verifier_node_id=verifier_node_id,
    )


def _coerce_signal(item: Any) -> GroundTruthSignal:
    if isinstance(item, GroundTruthSignal):
        return item
    return GroundTruthSignal(
        id=str(item["id"]),
        kind=str(item["kind"]),
        artifact_pointer=str(item["artifact_pointer"]),
        passed=bool(item["passed"]),
        message=str(item.get("message", "")),
    )


def _stable_unique(items: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(item) for item in items))
