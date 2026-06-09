"""Command-node execution helpers for the conductor."""

from __future__ import annotations

from typing import Any

from .runners import classify_exit
from .types import NodeSpec, ResultEnvelope


def run_command_node(node: NodeSpec, outcome: Any) -> ResultEnvelope:
    """Build the result envelope for a test/verify command-node outcome."""
    ok = outcome.exit_code == 0
    streams = (outcome.stdout or "") + (outcome.stderr or "")
    return ResultEnvelope(
        node_id=node.id,
        idempotency_key=node.idempotency_key,
        status="succeeded" if ok else "failed",
        error_class=classify_exit(outcome),
        artifact={"exit_code": outcome.exit_code, "command": list(node.command or [])},
        stdout_ref=streams or None,
        token_usage={
            "input": 0,
            "thinking": 0,
            "output": 0,
            "cached": 0,
            "accounting": "exact",
        },
    )
