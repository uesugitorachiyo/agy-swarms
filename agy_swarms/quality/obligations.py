"""FR-25 / AC-30 obligation extraction and non-self closure verification.

The extractor is deliberately a fixed grammar pass, not an LLM judgment: it emits every
line containing an RFC-2119 ``SHALL``/``MUST``/``SHOULD`` clause plus every parsed
``FR-``/``NFR-``/``CON-``/``AC-`` id. LLM proposals may add obligations, but they cannot
drop, merge away, or weaken obligations extracted by this pass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Iterable, Sequence

__all__ = [
    "ClosureStatus",
    "Obligation",
    "ObligationClosureReport",
    "ObligationMergeError",
    "SynthesisHandoff",
    "VerificationSignal",
    "closure_status",
    "evaluate_obligation_closure",
    "extract_obligations",
    "merge_llm_obligations",
]


_RFC2119 = re.compile(r"\b(?:SHALL|MUST|SHOULD)(?:\s+NOT)?\b")
_REQ_ID = re.compile(r"\b(?:FR|NFR|CON|AC)-[A-Z0-9]+(?:\.[0-9]+)?\b")
_LEADING_LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s*")
_GROUND_TRUTH_KINDS = {"test", "lint", "compile", "schema", "judge"}


@dataclass(frozen=True)
class Obligation:
    """One extracted or proposed closure obligation."""

    id: str
    text: str
    source: str
    source_ref: str


@dataclass(frozen=True)
class VerificationSignal:
    """A cited closure signal bound to an obligation (FR-25/CON-3)."""

    obligation_id: str
    kind: str
    artifact_pointer: str
    producer_node_id: str
    verifier_node_id: str
    verdict: str


@dataclass(frozen=True)
class ClosureStatus:
    """Whether a set of obligations has enough non-self evidence to close."""

    closable: bool
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class SynthesisHandoff:
    """Closure concerns that must be carried into final synthesis."""

    closure_status: str
    obligation_ids: tuple[str, ...]
    unresolved_concerns: tuple[str, ...] = ()


@dataclass(frozen=True)
class ObligationClosureReport:
    """AC-4 closure evidence derived from deterministic obligation extraction."""

    obligations: tuple[Obligation, ...]
    status: ClosureStatus
    synthesis_handoff: SynthesisHandoff


class ObligationMergeError(Exception):
    """Raised when an LLM proposal drops, merges away, or weakens extracted obligations."""


def extract_obligations(spec_text: str) -> list[Obligation]:
    """Extract the deterministic FR-25 obligation set from ``spec_text``.

    RFC-2119 clauses are emitted in source order with stable ``clause:NNNN`` ids. Parsed
    requirement ids are de-duplicated and emitted lexicographically after the clauses.
    """
    obligations: list[Obligation] = []
    clause_index = 0
    for line_no, raw_line in enumerate(spec_text.splitlines(), start=1):
        text = _LEADING_LIST_MARKER.sub("", raw_line).strip()
        if not text or _RFC2119.search(text) is None:
            continue
        clause_index += 1
        obligations.append(
            Obligation(
                id=f"clause:{clause_index:04d}",
                text=text,
                source="rfc2119",
                source_ref=f"line:{line_no}",
            )
        )

    for req_id in sorted(set(_REQ_ID.findall(spec_text))):
        obligations.append(
            Obligation(
                id=f"id:{req_id}",
                text=req_id,
                source="requirement_id",
                source_ref=f"id:{req_id}",
            )
        )
    return obligations


def merge_llm_obligations(
    extracted: Sequence[Obligation], proposed: Sequence[Obligation]
) -> list[Obligation]:
    """Merge LLM-added obligations without allowing mutation of extracted ones.

    The proposal must preserve each extracted obligation byte-for-byte by id. Extra
    proposal ids are appended in proposal order. Any missing extracted id or text/source
    mutation is treated as a drop/weaken/merge-away attempt and rejected.
    """
    proposed_by_id = {obligation.id: obligation for obligation in proposed}
    rejected: list[str] = []
    for obligation in extracted:
        candidate = proposed_by_id.get(obligation.id)
        if candidate is None:
            rejected.append(f"{obligation.id}: missing")
            continue
        if candidate.text != obligation.text:
            rejected.append(f"{obligation.id}: changed text")
            continue
        if candidate.source != obligation.source or candidate.source_ref != obligation.source_ref:
            rejected.append(f"{obligation.id}: changed provenance")

    if rejected:
        detail = "; ".join(rejected)
        raise ObligationMergeError(
            f"LLM proposal cannot drop or weaken extracted obligations: {detail}"
        )

    extracted_ids = {obligation.id for obligation in extracted}
    merged = list(extracted)
    for obligation in proposed:
        if obligation.id not in extracted_ids:
            merged.append(obligation)
    return merged


def closure_status(
    obligations: Sequence[Obligation], signals: Iterable[VerificationSignal]
) -> ClosureStatus:
    """Return closeable only when every obligation has a valid non-self signal."""
    valid_signal_ids = {signal.obligation_id for signal in signals if _is_valid_signal(signal)}
    blockers = tuple(
        f"{obligation.id}: no non-self passing verification with artifact pointer"
        for obligation in obligations
        if obligation.id not in valid_signal_ids
    )
    return ClosureStatus(closable=not blockers, blockers=blockers)


def evaluate_obligation_closure(
    spec_text: str,
    signals: Iterable[VerificationSignal],
) -> ObligationClosureReport:
    """Extract obligations, verify closure, and preserve blockers for synthesis."""
    obligations = tuple(extract_obligations(spec_text))
    status = closure_status(obligations, signals)
    return ObligationClosureReport(
        obligations=obligations,
        status=status,
        synthesis_handoff=SynthesisHandoff(
            closure_status="closed" if status.closable else "blocked",
            obligation_ids=tuple(obligation.id for obligation in obligations),
            unresolved_concerns=status.blockers,
        ),
    )


def _is_valid_signal(signal: VerificationSignal) -> bool:
    return (
        signal.kind in _GROUND_TRUTH_KINDS
        and signal.verdict == "passed"
        and bool(signal.artifact_pointer.strip())
        and signal.producer_node_id != signal.verifier_node_id
    )
