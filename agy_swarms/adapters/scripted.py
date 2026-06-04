"""FR-17 scripted adapter — zero-token deterministic replay (AC-S1/AC-S2).

The ``scripted`` adapter maps a node (by ``id``, else ``idempotency_key``) to a *canned*
``ResultEnvelope``: it replays planted outputs — successes, failures, timeouts,
budget-overruns, malformed artifacts — while spending ZERO model tokens and declaring
``accounting=exact``. It reads NO wall-clock / RNG / ambient I/O, so two runs of the same
node produce byte-identical envelopes (``started_at``/``ended_at`` stay ``""``). That
determinism is the substrate the whole AC-1 Phase-1 gate runs against.

Division of labour (§D.2): the adapter only *replays what is planted*. Schema validation,
``error_class``→``FailureClass`` classification, and the fail-closed rule are the
conductor's job — this module never interprets the artifact it returns.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ..types import ErrorClass, NodeSpec, ResultEnvelope

__all__ = ["CannedResult", "ScriptedAdapter", "ScriptedAdapterError"]

# The zero-token usage block every canned result defaults to (§D.2 / FR-17).
_ZERO_USAGE: dict[str, Any] = {
    "input": 0,
    "thinking": 0,
    "output": 0,
    "cached": 0,
    "accounting": "exact",
}


class ScriptedAdapterError(Exception):
    """Raised when no canned result is planted for a dispatched node (FR-17)."""


@dataclass
class CannedResult:
    """One planted outcome the adapter replays into a ``ResultEnvelope`` (FR-17).

    ``token_usage=None`` (the default) replays as the zero-token block; a planted block
    (e.g. a budget-overrun) is replayed verbatim with ``accounting=exact`` stamped if
    absent. ``status``/``error_class`` carry the planted failure mode; ``artifact`` is
    returned untouched (a *malformed* artifact is the adapter's job to deliver, not to
    reject — that is the conductor's).
    """

    status: str = "succeeded"  # succeeded | failed | timed_out | cancelled
    artifact: dict[str, Any] = field(default_factory=dict)
    error_class: ErrorClass = ErrorClass.NONE
    token_usage: dict[str, Any] | None = None
    cost_usd: float = 0.0
    concerns: list[str] = field(default_factory=list)
    blockers: list[dict[str, str]] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    pointers: list[str] = field(default_factory=list)


class ScriptedAdapter:
    """Deterministic, zero-token replay adapter (FR-17).

    ``transcript`` maps a node ``id`` *or* ``idempotency_key`` to a ``CannedResult``.
    ``accounting`` is ``exact`` because every byte of usage is known up front. ``seed`` is
    carried for parity with live adapters (the scripted path consumes no randomness).
    ``capabilities`` backs the FR-13 cover check used by AC-35 fallback selection.
    """

    accounting = "exact"

    def __init__(
        self,
        transcript: Mapping[str, CannedResult],
        *,
        seed: int = 0,
        capabilities: Iterable[str] = frozenset(),
    ) -> None:
        self.transcript: dict[str, CannedResult] = dict(transcript)
        self.seed = seed
        self.capabilities: frozenset[str] = frozenset(capabilities)
        self.name = "scripted"

    def covers(self, required_capabilities: Iterable[str]) -> bool:
        """True iff this adapter declares every required capability (FR-13)."""
        return set(required_capabilities) <= self.capabilities

    def run(
        self,
        node: NodeSpec,
        *,
        attempt: int = 0,
        reservation_id: str | None = None,
    ) -> ResultEnvelope:
        """Replay the canned result for ``node`` as a fully-stamped envelope (§D.2).

        Stamps node identity, ``attempt`` and ``reservation_id`` from the dispatch so the
        conductor can correlate; leaves timestamps empty (no wall-clock) so the envelope is
        byte-identical across runs. Raises ``ScriptedAdapterError`` if nothing is planted.
        """
        canned = self._lookup(node)
        usage = dict(canned.token_usage) if canned.token_usage is not None else dict(_ZERO_USAGE)
        usage.setdefault("accounting", "exact")
        return ResultEnvelope(
            node_id=node.id,
            idempotency_key=node.idempotency_key,
            status=canned.status,
            attempt=attempt,
            adapter=self.name,
            model=f"scripted:{node.model_tier}",
            thinking_level="none",
            reservation_id=reservation_id,
            started_at="",
            ended_at="",
            error_class=canned.error_class,
            artifact=dict(canned.artifact),
            pointers=list(canned.pointers),
            changed_files=list(canned.changed_files),
            concerns=list(canned.concerns),
            blockers=[dict(b) for b in canned.blockers],
            token_usage=usage,
            cost_usd=canned.cost_usd,
        )

    def _lookup(self, node: NodeSpec) -> CannedResult:
        for key in (node.id, node.idempotency_key):
            if key and key in self.transcript:
                return self.transcript[key]
        raise ScriptedAdapterError(
            f"scripted: no canned result for node {node.id!r} "
            f"(idempotency_key {node.idempotency_key!r})"
        )
