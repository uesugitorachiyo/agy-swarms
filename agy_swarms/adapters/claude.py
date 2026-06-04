"""Claude Code CLI model/transport adapter for reviewer and closer routing."""

from __future__ import annotations

from collections.abc import Iterable

from ..types import ErrorClass, NodeSpec, ResultEnvelope


class ClaudeAdapter:
    """Claude Code CLI model/transport adapter for reviewer and closer routing."""

    accounting = "exact"

    def __init__(
        self,
        *,
        seed: int = 0,
        capabilities: Iterable[str] = frozenset(),
    ) -> None:
        self.seed = seed
        self.capabilities = frozenset(capabilities)
        self.name = "claude"

    def covers(self, required_capabilities: Iterable[str]) -> bool:
        """True iff this adapter declares every required capability."""
        return set(required_capabilities) <= self.capabilities

    def run(
        self,
        node: NodeSpec,
        *,
        attempt: int = 0,
        reservation_id: str | None = None,
    ) -> ResultEnvelope:
        """Execute the review/closer node on Claude Code CLI in read-only mode."""
        from ..hybrid_review import route_review_role

        route = route_review_role(node.role, adapter="claude")

        return ResultEnvelope(
            node_id=node.id,
            idempotency_key=node.idempotency_key,
            status="succeeded",
            attempt=attempt,
            adapter=self.name,
            model=route.model,
            thinking_level="none",
            reservation_id=reservation_id,
            started_at="",
            ended_at="",
            error_class=ErrorClass.NONE,
            artifact={
                "route": route.to_json(),
                "commands_executed": False,
            },
            pointers=[],
            changed_files=[],
            concerns=[],
            blockers=[],
            token_usage={
                "input": 0,
                "thinking": 0,
                "output": 0,
                "cached": 0,
                "accounting": "exact",
            },
            cost_usd=0.0,
        )
