"""Review budget alert and auto-triage event helpers."""

from __future__ import annotations

from typing import Any


def review_budget_events(
    *,
    node_id: str,
    role: str,
    spent_tokens: int,
    closer: str,
    threshold: int = 1000,
) -> tuple[list[dict[str, Any]], str]:
    """Return review budget events and the resulting closer adapter."""
    if role not in ("reviewer", "closer") or spent_tokens <= threshold:
        return [], closer

    events: list[dict[str, Any]] = [
        {
            "type": "review_budget_alert",
            "node_id": node_id,
            "role": role,
            "spent_tokens": spent_tokens,
            "threshold": threshold,
            "warning": (
                f"Review role node '{node_id}' exceeded lightweight token guardrail "
                f"threshold ({threshold} tokens) with {spent_tokens} tokens."
            ),
        }
    ]

    if role != "reviewer" or closer not in ("agy", "codex"):
        return events, closer

    new_closer = "codex" if closer == "agy" else "off"
    events.append(
        {
            "type": "review_auto_triage",
            "node_id": node_id,
            "action": "downgrade_closer",
            "previous_closer": closer,
            "new_closer": new_closer,
            "warning": (
                f"Reviewer node '{node_id}' exceeded budget threshold. Closer adapter "
                f"downgraded from '{closer}' to '{new_closer}' to conserve remaining budget."
            ),
        }
    )
    return events, new_closer
