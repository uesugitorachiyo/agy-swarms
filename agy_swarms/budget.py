"""§D.4 budget: the caps-driven estimator, the deterministic split, and BudgetLedger.

``est()`` is the single load-bearing admission/retry/MapSpec-split estimator — it is
**caps-driven, not tier-driven** (§D.4 line 324): the per-call billable-token ceiling is
``caps.max_output_tokens + caps.max_thinking_tokens`` (thinking billed as output), NOT
``max_turns × per-turn``.

``split_budget`` implements the §D.1.2 (line 219) deterministic split with **no
floating-point division**, so per-child caps — a hashed field folded into each child's
``idempotency_key`` — stay byte-identical across implementations: floor each share, then
distribute the remainder one unit at a time in ascending child-index order.

``BudgetLedger`` is the reserve→commit/release protocol (§D.4). Entries are keyed by
``(epoch_seq, node_id)`` — the **monotonic** ordering counter, NEVER ``epoch_id`` (a
content hash can repeat after a revert and collide a post-revert reservation with a
still-open prior one — the double-spend hazard, §D.4 line 353). Aggregates are **derived**
from entries so they can never drift. Admission is cumulative-across-attempts: a node that
already consumed part of its ceiling cannot reserve a fresh full ceiling (AC-1, line 476).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .types import NodeSpec, ResultEnvelope

__all__ = [
    "est",
    "split_budget",
    "aggregate_token_usage",
    "Dims",
    "TokenUsageSummary",
    "Admission",
    "LedgerEntry",
    "BudgetLedger",
    "BudgetError",
]


def est(node: NodeSpec) -> int:
    """Caps-driven per-call billable-token ceiling (§D.4).

    ``est(node) = caps.max_output_tokens + caps.max_thinking_tokens`` — thinking counted
    as output (AC-0 cost-ledger rule). ``max_turns`` does NOT multiply this (it caps loop
    iterations, not tokens); ``max_tool_calls`` is a call-count cap, not a token quantity.
    """
    return node.caps.max_output_tokens + node.caps.max_thinking_tokens


def split_budget(total: int, n: int, weights: Sequence[int] | None = None) -> list[int]:
    """Split ``total`` across ``n`` children deterministically (§D.1.2).

    Equal split (no ``weights``): ``child_i = floor(total / n)``; the remainder
    ``total mod n`` is distributed one unit at a time in ascending child-index order.
    Weighted split: ``child_i = floor(total * w_i / sum(w))`` with the leftover
    ``total - Σ floor(...)`` distributed the same way. Integer-only — no float division —
    so the result is byte-identical across implementations. Conserves ``total`` exactly.
    """
    if n <= 0:
        raise ValueError("split_budget requires n >= 1")
    if weights is None:
        share = total // n
        base = [share] * n
        remainder = total - share * n
    else:
        if len(weights) != n:
            raise ValueError("weights length must equal n")
        if any(w < 0 for w in weights):
            raise ValueError("weights must be non-negative")
        wsum = sum(weights)
        if wsum <= 0:
            raise ValueError("weights must sum to a positive value")
        base = [(total * w) // wsum for w in weights]
        remainder = total - sum(base)
    for i in range(remainder):
        base[i] += 1
    return base


class BudgetError(Exception):
    """Raised on an illegal ledger transition (e.g. commit without a reservation)."""


@dataclass(frozen=True)
class TokenUsageSummary:
    """Aggregated token/cost instrumentation over result envelopes."""

    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cached_tokens: int = 0
    billable_equivalent_tokens: int = 0
    cost_usd: float = 0.0
    accounting_modes: dict[str, int] | None = None
    concerns: list[str] | None = None


def aggregate_token_usage(envelopes: Sequence[ResultEnvelope]) -> TokenUsageSummary:
    """Aggregate adapter-reported token usage for run-level instrumentation.

    Billable-equivalent tokens count output plus thinking tokens here; cached input/USD
    pricing is reported separately by later M2 ledgers once exact provider cache ratios
    are available. Opaque accounting is never hidden: each opaque envelope emits a concern.
    """
    input_tokens = 0
    output_tokens = 0
    thinking_tokens = 0
    cached_tokens = 0
    cost_usd = 0.0
    accounting_modes: dict[str, int] = {}
    concerns: list[str] = []
    for envelope in envelopes:
        usage = envelope.token_usage
        input_tokens += int(usage.get("input", 0))
        output_tokens += int(usage.get("output", 0))
        thinking_tokens += int(usage.get("thinking", 0))
        cached_tokens += int(usage.get("cached", 0))
        cost_usd += float(envelope.cost_usd)
        accounting = str(usage.get("accounting", "unknown"))
        accounting_modes[accounting] = accounting_modes.get(accounting, 0) + 1
        if accounting == "opaque":
            concerns.append(f"{envelope.node_id}: opaque token accounting")
    return TokenUsageSummary(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
        cached_tokens=cached_tokens,
        billable_equivalent_tokens=output_tokens + thinking_tokens,
        cost_usd=cost_usd,
        accounting_modes=accounting_modes,
        concerns=concerns,
    )


@dataclass(frozen=True)
class Dims:
    """A 2-dimension budget vector: billable ``tokens`` (the gating dim) and ``usd``."""

    tokens: int = 0
    usd: float = 0.0

    def __add__(self, other: Dims) -> Dims:
        return Dims(self.tokens + other.tokens, self.usd + other.usd)

    def __sub__(self, other: Dims) -> Dims:
        return Dims(self.tokens - other.tokens, self.usd - other.usd)

    def fits_within(self, cap: Dims) -> bool:
        """True iff this vector is ≤ ``cap`` in **every** dimension."""
        return self.tokens <= cap.tokens and self.usd <= cap.usd

    def exceeds(self, cap: Dims) -> bool:
        """True iff this vector is > ``cap`` in **any** dimension."""
        return self.tokens > cap.tokens or self.usd > cap.usd

    @staticmethod
    def max(a: Dims, b: Dims) -> Dims:
        """Per-dimension maximum (the opaque reserved-floor rule, §D.4)."""
        return Dims(max(a.tokens, b.tokens), max(a.usd, b.usd))


@dataclass
class LedgerEntry:
    """One ``(epoch_seq, node_id)`` row (§D.4 BudgetLedger shape).

    ``reserved`` is the CURRENT open reservation (zeroed on commit/release); ``committed``
    is the cumulative-across-attempts charge; ``epoch_id`` is a non-key audit field
    recording the content identity active when the reservation was taken (§D.4 line 353).
    """

    epoch_seq: int
    node_id: str
    epoch_id: str
    reserved: Dims
    committed: Dims
    status: str  # reserved | committed | released | overspend
    reservation_id: str
    subtree: str | None = None


@dataclass(frozen=True)
class Admission:
    """Outcome of a ``reserve`` admission decision (no state change when rejected)."""

    admitted: bool
    reservation_id: str | None = None
    reason: str | None = None  # node-ceiling | subtree | global


class BudgetLedger:
    """Reserve→commit/release ledger with cumulative admission + orphan sweep (§D.4)."""

    def __init__(self, limit: Dims, *, opaque_multiplier: int = 1) -> None:
        self.limit = limit
        self.opaque_multiplier = opaque_multiplier
        self.entries: dict[tuple[int, str], LedgerEntry] = {}
        self.subtree_limits: dict[str, Dims] = {}
        self.concerns: list[str] = []

    # --- derived aggregates (never drift) ----------------------------------

    @property
    def reserved(self) -> Dims:
        out = Dims()
        for e in self.entries.values():
            out = out + e.reserved
        return out

    @property
    def spent(self) -> Dims:
        out = Dims()
        for e in self.entries.values():
            out = out + e.committed
        return out

    @property
    def available(self) -> Dims:
        return self.limit - self.reserved - self.spent

    # --- subtree accounting (§D.4 line 355) --------------------------------

    def register_subtree(self, root_id: str, limit: Dims) -> None:
        self.subtree_limits[root_id] = limit

    def subtree_reserved(self, root_id: str) -> Dims:
        out = Dims()
        for e in self.entries.values():
            if e.subtree == root_id:
                out = out + e.reserved
        return out

    def subtree_spent(self, root_id: str) -> Dims:
        out = Dims()
        for e in self.entries.values():
            if e.subtree == root_id:
                out = out + e.committed
        return out

    def subtree_available(self, root_id: str) -> Dims:
        return (
            self.subtree_limits[root_id]
            - self.subtree_reserved(root_id)
            - self.subtree_spent(root_id)
        )

    # --- reserve / commit / release ----------------------------------------

    def reserve(
        self,
        epoch_seq: int,
        node_id: str,
        node: NodeSpec,
        *,
        epoch_id: str = "",
        budget_consumed: Dims | None = None,
        subtree: str | None = None,
        accounting: str = "exact",
    ) -> Admission:
        """Atomically admit a reservation for ``(epoch_seq, node_id)`` or reject it.

        Idempotent per node (FR-30.1): a second reserve while one is already open returns
        the existing admission and double-counts nothing. Admission tests, in order:
        (a) node ceiling — ``budget_consumed + est(node) ≤ est(node)`` (cumulative across
        attempts, §D.4 line 359); (b) remaining subtree budget; (c) remaining global
        budget — all three must hold.
        """
        key = (epoch_seq, node_id)
        existing = self.entries.get(key)
        if existing is not None and existing.status == "reserved":
            return Admission(True, existing.reservation_id)

        consumed = budget_consumed or Dims()
        per_call = est(node)
        multiplier = self.opaque_multiplier if accounting == "opaque" else 1
        amount = Dims(tokens=per_call * multiplier, usd=0.0)

        # (a) node ceiling — cumulative across attempts (§D.4 lines 354/359): est(node)
        # is BOTH this attempt's projected reservation and the node's cumulative ceiling,
        # so any prior spend leaves no room for a fresh full reservation (AC-1, line 476).
        projected = per_call
        node_ceiling = per_call
        if consumed.tokens + projected > node_ceiling:
            return Admission(False, None, "node-ceiling")
        # (b) subtree
        if subtree is not None and not amount.fits_within(self.subtree_available(subtree)):
            return Admission(False, None, "subtree")
        # (c) global
        if not amount.fits_within(self.available):
            return Admission(False, None, "global")

        reservation_id = f"resv:{epoch_seq}:{node_id}"
        carried = existing.committed if existing is not None else Dims()
        self.entries[key] = LedgerEntry(
            epoch_seq=epoch_seq,
            node_id=node_id,
            epoch_id=epoch_id,
            reserved=amount,
            committed=carried,
            status="reserved",
            reservation_id=reservation_id,
            subtree=subtree,
        )
        return Admission(True, reservation_id)

    def commit(
        self,
        epoch_seq: int,
        node_id: str,
        actual: Dims | None,
        *,
        accounting: str = "exact",
    ) -> None:
        """Reconcile a reservation (FR-6.2): replace it with the actual charge.

        Exact accounting releases the delta (``actual``); opaque never releases below the
        reserved floor (``max(actual, reserved)``); a missing count (``actual is None``)
        charges the full reservation and records a ``concern``. ``actual`` exceeding the
        reservation in any dimension marks the entry ``overspend`` (the bounded-overrun
        case, FR-6.6). The charge accumulates into ``committed`` (cumulative, §D.1).
        """
        entry = self.entries.get((epoch_seq, node_id))
        if entry is None or entry.status != "reserved":
            raise BudgetError(f"commit without an open reservation for ({epoch_seq}, {node_id!r})")
        reserved_amt = entry.reserved
        if actual is None:
            charged = reserved_amt
            self.concerns.append(
                f"{node_id}: no token count returned; charged full reservation (§D.4)"
            )
            status = "committed"
        elif accounting == "opaque":
            charged = Dims.max(actual, reserved_amt)
            status = "overspend" if actual.exceeds(reserved_amt) else "committed"
        else:
            charged = actual
            status = "overspend" if actual.exceeds(reserved_amt) else "committed"

        entry.committed = entry.committed + charged
        entry.reserved = Dims()
        entry.status = status

    def release(self, epoch_seq: int, node_id: str) -> None:
        """Return an open reservation to the pool (idempotent; no-op if none open)."""
        entry = self.entries.get((epoch_seq, node_id))
        if entry is None or entry.status != "reserved":
            return
        entry.reserved = Dims()
        entry.status = "released"

    def sweep_orphans(self) -> list[str]:
        """Release every open reservation with no commit, across ALL epoch_seq (FR-30).

        A current-epoch-only sweep is forbidden: ``epoch_seq`` is global/monotonic and an
        operator MAY bump it between crash and resume, so prior-epoch reservations would
        otherwise leak permanently against the ceiling (§D.4/§D.6). Returns the node ids
        whose orphan reservations were released.
        """
        released: list[str] = []
        for entry in self.entries.values():
            if entry.status == "reserved":
                entry.reserved = Dims()
                entry.status = "released"
                released.append(entry.node_id)
        return released

    def check_multiplier_drift(
        self, spot_check_multiplier: float, baseline_multiplier: float
    ) -> bool:
        """Check if spot-check multiplier drifts by >10% from its baseline value.

        A drift alarm fires when a spot-check multiplier deviates >10% from the baseline.
        On a fired alarm, cached USD/cost figures derived from the stale multiplier are
        invalidated (zeroed out) and a warning concern is raised.
        """
        if baseline_multiplier <= 0:
            return False

        drift = abs(spot_check_multiplier - baseline_multiplier) / baseline_multiplier
        if drift > 0.10:
            msg = (
                f"Multiplier drift detected: spot-check multiplier {spot_check_multiplier} "
                f"deviates from baseline {baseline_multiplier} by {drift:.2%} (>10%). "
                f"Invalidation triggered, recalibration scheduled."
            )
            if msg not in self.concerns:
                self.concerns.append(msg)
            # Invalidate cached USD/cost figures
            for key, entry in self.entries.items():
                self.entries[key] = LedgerEntry(
                    epoch_seq=entry.epoch_seq,
                    node_id=entry.node_id,
                    epoch_id=entry.epoch_id,
                    reserved=Dims(tokens=entry.reserved.tokens, usd=0.0),
                    committed=Dims(tokens=entry.committed.tokens, usd=0.0),
                    status=entry.status,
                    reservation_id=entry.reservation_id,
                    subtree=entry.subtree,
                )
            return True
        return False
