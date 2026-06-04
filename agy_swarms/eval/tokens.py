"""D5.3 M2 billable-equivalent token ledger."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

__all__ = [
    "M2GateStatus",
    "TokenLedgerIncomplete",
    "TokenLedgerReport",
    "TokenLedgerRow",
    "TokenRowKind",
    "build_token_report",
    "parse_cache_multiplier",
]


class M2GateStatus(StrEnum):
    """M2 token gate status."""

    PASSED = "passed"
    FAILED = "failed"


class TokenRowKind(StrEnum):
    """Cost-bearing row classes that Phase 5 must account for."""

    WORKER = "worker"
    JUDGE = "judge"
    RETRY = "retry"
    OPTIMIZER_REVISION = "optimizer_revision"
    ESCALATION = "escalation"
    CACHE_WRITE = "cache_write"
    OPAQUE_ADAPTER_CALIBRATION = "opaque_adapter_calibration"
    TOOL_IO = "tool_io"


class TokenLedgerIncomplete(ValueError):
    """Raised when M2 cannot gate because mandatory accounting evidence is absent."""


@dataclass(frozen=True)
class TokenLedgerRow:
    """One token-accounting row."""

    id: str
    kind: TokenRowKind
    input_uncached: int = 0
    output: int = 0
    cached_read: int = 0
    note: str = ""

    def billable_equivalent_tokens(self, cache_mult: float) -> int:
        """Compute conservative billable-equivalent tokens for this row."""
        _validate_nonnegative(self.input_uncached, "input_uncached")
        _validate_nonnegative(self.output, "output")
        _validate_nonnegative(self.cached_read, "cached_read")
        return math.ceil(self.input_uncached + self.output + (self.cached_read * cache_mult))


@dataclass(frozen=True)
class TokenLedgerReport:
    """M2 gate report over one candidate ledger."""

    status: M2GateStatus
    billable_equivalent_tokens: int
    threshold_tokens: int
    opus_baseline_billable_tokens: int
    target_ratio: float
    cache_mult: float
    rows: tuple[TokenLedgerRow, ...]
    row_counts_by_kind: dict[str, int]
    reported_only: dict[str, Any]


REQUIRED_ROW_KINDS: tuple[TokenRowKind, ...] = (
    TokenRowKind.WORKER,
    TokenRowKind.JUDGE,
    TokenRowKind.RETRY,
    TokenRowKind.OPTIMIZER_REVISION,
    TokenRowKind.ESCALATION,
    TokenRowKind.CACHE_WRITE,
    TokenRowKind.OPAQUE_ADAPTER_CALIBRATION,
    TokenRowKind.TOOL_IO,
)


def build_token_report(
    *,
    rows: tuple[TokenLedgerRow, ...],
    cache_mult: float | None,
    opus_baseline_billable_tokens: int,
    target_ratio: float,
    required_kinds: tuple[TokenRowKind, ...] = REQUIRED_ROW_KINDS,
    factory_v3_baseline_billable_tokens: int | None = None,
) -> TokenLedgerReport:
    """Build a fail-closed M2 report for the candidate token ledger."""
    if cache_mult is None or cache_mult <= 0:
        raise TokenLedgerIncomplete("cache_mult is required before M2 can gate")
    if opus_baseline_billable_tokens <= 0:
        raise TokenLedgerIncomplete("opus billable token baseline must be positive")
    if target_ratio <= 0:
        raise TokenLedgerIncomplete("m2 target_ratio must be positive")
    if not rows:
        raise TokenLedgerIncomplete("token ledger rows are required before M2 can gate")

    counts = _row_counts(rows)
    missing = [kind.value for kind in required_kinds if counts.get(kind.value, 0) == 0]
    if missing:
        raise TokenLedgerIncomplete(f"missing token ledger row kind(s): {', '.join(missing)}")

    billable = sum(row.billable_equivalent_tokens(cache_mult) for row in rows)
    threshold = math.floor(opus_baseline_billable_tokens * target_ratio)
    reported_only: dict[str, Any] = {
        "factory_v3_token_baseline": "missing_reported_only",
    }
    if factory_v3_baseline_billable_tokens is not None:
        reported_only["factory_v3_token_baseline"] = "present_reported_only"
        reported_only["factory_v3_billable_equivalent_tokens"] = factory_v3_baseline_billable_tokens

    return TokenLedgerReport(
        status=M2GateStatus.PASSED if billable < threshold else M2GateStatus.FAILED,
        billable_equivalent_tokens=billable,
        threshold_tokens=threshold,
        opus_baseline_billable_tokens=opus_baseline_billable_tokens,
        target_ratio=target_ratio,
        cache_mult=cache_mult,
        rows=rows,
        row_counts_by_kind=counts,
        reported_only=reported_only,
    )


def parse_cache_multiplier(value: str) -> float:
    """Extract the numeric multiplier from the Phase-0 cache multiplier pin."""
    if not value:
        raise TokenLedgerIncomplete("cache_mult is required before M2 can gate")
    match = re.search(r"(?:OPAQUE_)?([0-9]+(?:\.[0-9]+)?)", value)
    if not match:
        raise TokenLedgerIncomplete(f"cache_mult is not parseable: {value}")
    cache_mult = float(match.group(1))
    if cache_mult <= 0:
        raise TokenLedgerIncomplete("cache_mult must be positive")
    return cache_mult


def _row_counts(rows: tuple[TokenLedgerRow, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.kind.value] = counts.get(row.kind.value, 0) + 1
    return counts


def _validate_nonnegative(value: int, field: str) -> None:
    if value < 0:
        raise TokenLedgerIncomplete(f"{field} must be non-negative")
