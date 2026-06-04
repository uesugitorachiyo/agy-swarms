"""FR-24 loop-until-dry discovery predicate."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "DiscoveryReport",
    "DiscoveryRound",
    "DiscoveryStatus",
    "DiscoveryStep",
    "loop_until_dry",
]


class DiscoveryStatus(StrEnum):
    """Code-owned discovery loop termination status."""

    DRY = "dry"
    MAX_ITERATIONS = "max_iterations"


@dataclass(frozen=True)
class DiscoveryRound:
    """One discovery iteration's emitted coverage item ids."""

    id: str
    item_ids: tuple[str, ...]


@dataclass(frozen=True)
class DiscoveryStep:
    """One deterministic discovery diff."""

    round_id: str
    item_ids: tuple[str, ...]
    new_item_ids: tuple[str, ...]
    discovered_item_ids: tuple[str, ...]
    dry: bool


@dataclass(frozen=True)
class DiscoveryReport:
    """Bounded loop-until-dry discovery report."""

    status: DiscoveryStatus
    terminated: bool
    iterations: int
    discovered_item_ids: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    steps: tuple[DiscoveryStep, ...] = ()


def loop_until_dry(
    rounds: tuple[DiscoveryRound, ...],
    *,
    max_iterations: int,
) -> DiscoveryReport:
    """Run discovery rounds until no new item ids appear or the cap is reached."""
    if max_iterations <= 0:
        raise ValueError("max_iterations must be positive")

    discovered: tuple[str, ...] = ()
    steps: list[DiscoveryStep] = []
    for round_ in rounds[:max_iterations]:
        item_ids = _stable_unique(round_.item_ids)
        new_item_ids = tuple(item_id for item_id in item_ids if item_id not in discovered)
        discovered = discovered + new_item_ids
        step = DiscoveryStep(
            round_id=round_.id,
            item_ids=item_ids,
            new_item_ids=new_item_ids,
            discovered_item_ids=discovered,
            dry=not new_item_ids,
        )
        steps.append(step)
        if step.dry:
            return DiscoveryReport(
                status=DiscoveryStatus.DRY,
                terminated=True,
                iterations=len(steps),
                discovered_item_ids=discovered,
                steps=tuple(steps),
            )

    return DiscoveryReport(
        status=DiscoveryStatus.MAX_ITERATIONS,
        terminated=True,
        iterations=len(steps),
        discovered_item_ids=discovered,
        blockers=("max iterations reached before dry predicate",),
        steps=tuple(steps),
    )


def _stable_unique(items: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(item) for item in items))
