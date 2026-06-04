"""D6.1 declarative policy engine + tiered autonomy."""

from __future__ import annotations

import pytest

from agy_swarms.governance.policy import (
    ActionKind,
    ApprovalToken,
    PolicyAction,
    PolicyConfig,
    PolicyDecisionStatus,
    PolicyError,
    PolicyMode,
    RiskLevel,
    evaluate_policy,
)


def test_auto_allows_declared_low_risk_write_inside_sandbox():
    decision = evaluate_policy(
        PolicyAction(
            id="write-src",
            kind=ActionKind.WRITE,
            target="src/app.py",
            declared=True,
            within_sandbox=True,
            risk=RiskLevel.LOW,
        ),
        PolicyConfig(mode=PolicyMode.AUTO),
    )

    assert decision.status == PolicyDecisionStatus.ALLOWED
    assert decision.blockers == ()
    assert decision.concerns == ()


def test_batched_approval_queues_side_effects_into_digest():
    decision = evaluate_policy(
        PolicyAction(
            id="patch-1",
            kind=ActionKind.PATCH_PROMOTION,
            target="repo.patch",
            declared=True,
            within_sandbox=True,
            risk=RiskLevel.HIGH,
        ),
        PolicyConfig(mode=PolicyMode.BATCHED_APPROVAL),
    )

    assert decision.status == PolicyDecisionStatus.QUEUED
    assert decision.digest == ("patch-1: patch_promotion repo.patch (high risk)",)
    assert "approval required" in decision.concerns[0]


def test_strict_digest_blocks_until_approval_token_is_supplied():
    action = PolicyAction(
        id="shell-1",
        kind=ActionKind.SHELL,
        target="uv run pytest -q",
        declared=True,
        within_sandbox=True,
        risk=RiskLevel.HIGH,
    )

    blocked = evaluate_policy(action, PolicyConfig(mode=PolicyMode.STRICT_DIGEST))
    allowed = evaluate_policy(
        action,
        PolicyConfig(
            mode=PolicyMode.STRICT_DIGEST,
            approval_token=ApprovalToken(id="approval-1", approved_action_ids=("shell-1",)),
        ),
    )

    assert blocked.status == PolicyDecisionStatus.BLOCKED
    assert "strict digest approval required" in blocked.blockers[0]
    assert allowed.status == PolicyDecisionStatus.ALLOWED


def test_unknown_policy_mode_fails_closed():
    with pytest.raises(PolicyError, match="unknown policy mode"):
        PolicyConfig(mode="permissive")


def test_undeclared_network_action_blocks_in_auto_mode():
    decision = evaluate_policy(
        PolicyAction(
            id="network-1",
            kind=ActionKind.NETWORK,
            target="https://example.invalid",
            declared=False,
            within_sandbox=True,
            risk=RiskLevel.LOW,
        ),
        PolicyConfig(mode=PolicyMode.AUTO),
    )

    assert decision.status == PolicyDecisionStatus.BLOCKED
    assert "undeclared side effect" in decision.blockers[0]


def test_write_outside_sandbox_blocks_before_mode_specific_handling():
    decision = evaluate_policy(
        PolicyAction(
            id="write-escape",
            kind=ActionKind.WRITE,
            target="../escape.py",
            declared=True,
            within_sandbox=False,
            risk=RiskLevel.LOW,
        ),
        PolicyConfig(mode=PolicyMode.AUTO),
    )

    assert decision.status == PolicyDecisionStatus.BLOCKED
    assert "outside sandbox" in decision.blockers[0]
