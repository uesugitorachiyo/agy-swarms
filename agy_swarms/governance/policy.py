"""D6.1 declarative policy engine for side-effecting actions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "ActionKind",
    "ApprovalToken",
    "PolicyAction",
    "PolicyConfig",
    "PolicyDecision",
    "PolicyDecisionStatus",
    "PolicyError",
    "PolicyMode",
    "RiskLevel",
    "evaluate_policy",
]


class PolicyError(ValueError):
    """Raised when policy configuration is invalid."""


class PolicyMode(StrEnum):
    """Tiered autonomy modes."""

    AUTO = "auto"
    BATCHED_APPROVAL = "batched_approval"
    STRICT_DIGEST = "strict_digest"


class ActionKind(StrEnum):
    """Side-effect classes governed by the policy engine."""

    WRITE = "write"
    SHELL = "shell"
    NETWORK = "network"
    PATCH_PROMOTION = "patch_promotion"


class RiskLevel(StrEnum):
    """Risk classification supplied by the caller."""

    LOW = "low"
    HIGH = "high"


class PolicyDecisionStatus(StrEnum):
    """Policy outcome for one action."""

    ALLOWED = "allowed"
    QUEUED = "queued"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ApprovalToken:
    """Strict-digest approval over one or more action ids."""

    id: str
    approved_action_ids: tuple[str, ...]


@dataclass(frozen=True)
class PolicyConfig:
    """Policy configuration for a run or target."""

    mode: PolicyMode | str = PolicyMode.AUTO
    approval_token: ApprovalToken | None = None

    def __post_init__(self) -> None:
        try:
            mode = PolicyMode(self.mode)
        except ValueError as exc:
            raise PolicyError(f"unknown policy mode: {self.mode}") from exc
        object.__setattr__(self, "mode", mode)


@dataclass(frozen=True)
class PolicyAction:
    """One attempted side effect."""

    id: str
    kind: ActionKind
    target: str
    declared: bool
    within_sandbox: bool
    risk: RiskLevel = RiskLevel.LOW


@dataclass(frozen=True)
class PolicyDecision:
    """Decision emitted by the policy engine."""

    status: PolicyDecisionStatus
    action_id: str
    concerns: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    digest: tuple[str, ...] = ()


def evaluate_policy(action: PolicyAction, config: PolicyConfig) -> PolicyDecision:
    """Evaluate one side-effecting action under the configured autonomy tier."""
    blockers = _preflight_blockers(action)
    if blockers:
        return PolicyDecision(
            status=PolicyDecisionStatus.BLOCKED,
            action_id=action.id,
            blockers=blockers,
        )

    if config.mode == PolicyMode.AUTO:
        return PolicyDecision(status=PolicyDecisionStatus.ALLOWED, action_id=action.id)

    digest = (_digest_line(action),)
    if config.mode == PolicyMode.BATCHED_APPROVAL:
        return PolicyDecision(
            status=PolicyDecisionStatus.QUEUED,
            action_id=action.id,
            concerns=(f"approval required for {action.id}",),
            digest=digest,
        )

    if config.mode == PolicyMode.STRICT_DIGEST:
        if (
            config.approval_token is not None
            and action.id in config.approval_token.approved_action_ids
        ):
            return PolicyDecision(status=PolicyDecisionStatus.ALLOWED, action_id=action.id)
        return PolicyDecision(
            status=PolicyDecisionStatus.BLOCKED,
            action_id=action.id,
            blockers=(f"strict digest approval required for {action.id}",),
            digest=digest,
        )

    raise PolicyError(f"unknown policy mode: {config.mode}")


def _preflight_blockers(action: PolicyAction) -> tuple[str, ...]:
    blockers: list[str] = []
    if not action.id:
        blockers.append("action id is required")
    if not action.declared:
        blockers.append(f"undeclared side effect: {action.kind.value} {action.target}")
    if action.kind in {ActionKind.WRITE, ActionKind.PATCH_PROMOTION} and not action.within_sandbox:
        blockers.append(f"{action.kind.value} target is outside sandbox: {action.target}")
    return tuple(blockers)


def _digest_line(action: PolicyAction) -> str:
    return f"{action.id}: {action.kind.value} {action.target} ({action.risk.value} risk)"
