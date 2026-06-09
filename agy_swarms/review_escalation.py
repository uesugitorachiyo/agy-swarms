"""Deterministic review-disagreement escalation policy."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["EscalationDecision", "ReviewVerdict", "decide_review_escalation"]


@dataclass(frozen=True)
class ReviewVerdict:
    """One normalized reviewer/closer verdict for policy comparison."""

    source: str
    role: str
    verdict: str
    concerns: tuple[str, ...] = ()
    blockers: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class EscalationDecision:
    """A deterministic decision to request stronger follow-up review."""

    escalate: bool
    reason: str
    target_model: str = "gpt-5.5"
    reasoning_effort: str = "high"


_BLOCKING_VERDICTS = {"block"}
_PASSING_VERDICTS = {"pass"}
_CONCERN_VERDICTS = {"concerns", "block"}


def decide_review_escalation(
    primary: ReviewVerdict, secondary: ReviewVerdict
) -> EscalationDecision:
    """Decide if two review results disagree enough to require stronger Codex review."""
    primary_verdict = primary.verdict.casefold()
    secondary_verdict = secondary.verdict.casefold()

    if _is_pass_block_disagreement(primary_verdict, secondary_verdict):
        return EscalationDecision(escalate=True, reason="pass_block_disagreement")

    if _is_reviewer_concern_closer_pass(primary, secondary):
        return EscalationDecision(escalate=True, reason="reviewer_concern_closer_pass")

    if primary_verdict == secondary_verdict:
        return EscalationDecision(escalate=False, reason="review_verdicts_agree")

    return EscalationDecision(escalate=True, reason="review_verdicts_diverge")


def _is_pass_block_disagreement(first: str, second: str) -> bool:
    return (first in _PASSING_VERDICTS and second in _BLOCKING_VERDICTS) or (
        second in _PASSING_VERDICTS and first in _BLOCKING_VERDICTS
    )


def _is_reviewer_concern_closer_pass(primary: ReviewVerdict, secondary: ReviewVerdict) -> bool:
    verdicts = (primary, secondary)
    reviewer_has_concern = any(
        item.role == "reviewer"
        and (item.verdict.casefold() in _CONCERN_VERDICTS or bool(item.concerns))
        for item in verdicts
    )
    closer_passed = any(
        item.role == "closer" and item.verdict.casefold() == "pass" for item in verdicts
    )
    return reviewer_has_concern and closer_passed
