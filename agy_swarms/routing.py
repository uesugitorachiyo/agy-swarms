"""FR-19 complexity routing: code-owned fan-out gating for Phase 2.

This is the minimal Phase-2 activation seam. It is deliberately deterministic and
conservative: broad independent work can fan out, bounded multi-item review gets a small
fan-out, and unclear/narrow work fails closed to a single worker. The fuller AC-3 router
benchmark and live-classifier evaluation remain Phase 3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

__all__ = ["ComplexityDecision", "ComplexityRoute", "route_complexity"]


class ComplexityRoute(StrEnum):
    """FR-19 route classes."""

    SINGLE = "single"
    FANOUT_2_4 = "fanout(2-4)"
    FANOUT_10_PLUS = "fanout(10+)"


@dataclass(frozen=True)
class ComplexityDecision:
    """One deterministic code-owned route decision."""

    route: ComplexityRoute
    fanout: int
    reason: str
    concerns: tuple[str, ...] = ()


_NUMBER_WORDS = {
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_BREADTH_TERMS = (
    "independent",
    "parallel",
    "fan-out",
    "fanout",
    "suite",
    "documents",
    "aggregate",
    "summarize contradictions",
)
_NARROW_TERMS = (
    "one module",
    "one helper",
    "single file",
    "direct callers",
    "rename",
    "small",
    "trivial",
)


def route_complexity(task: str) -> ComplexityDecision:
    """Select single vs small fan-out vs large fan-out for ``task``.

    The rule is intentionally cheap and deterministic for Phase 2. It uses explicit
    breadth/count language from the task brief; model-informed classification can refine
    this in Phase 3 but must preserve the fail-closed single-agent default.
    """
    text = task.casefold()
    count = _largest_explicit_count(text)
    breadth_score = sum(1 for term in _BREADTH_TERMS if term in text)
    narrow_score = sum(1 for term in _NARROW_TERMS if term in text)

    if count >= 10 and breadth_score > 0:
        return ComplexityDecision(
            route=ComplexityRoute.FANOUT_10_PLUS,
            fanout=10,
            reason="broad_independent_breadth",
        )
    if 2 <= count <= 4 and breadth_score > 0 and narrow_score == 0:
        return ComplexityDecision(
            route=ComplexityRoute.FANOUT_2_4,
            fanout=count,
            reason="bounded_parallel_breadth",
        )
    if breadth_score >= 2 and narrow_score == 0:
        return ComplexityDecision(
            route=ComplexityRoute.FANOUT_2_4,
            fanout=4,
            reason="bounded_parallel_breadth",
        )
    if narrow_score > 0:
        return ComplexityDecision(
            route=ComplexityRoute.SINGLE,
            fanout=1,
            reason="narrow_or_sequential",
        )
    return ComplexityDecision(
        route=ComplexityRoute.SINGLE,
        fanout=1,
        reason="narrow_or_sequential",
        concerns=("default_single",),
    )


def _largest_explicit_count(text: str) -> int:
    counts = [int(match) for match in re.findall(r"\b\d+\b", text)]
    for word, value in _NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", text):
            counts.append(value)
    return max(counts, default=0)
