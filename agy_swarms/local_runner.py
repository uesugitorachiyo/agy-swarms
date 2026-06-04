"""Local deterministic graph execution for the v0.2 runner."""

from __future__ import annotations

from typing import Any

from .adapters.scripted import CannedResult, ScriptedAdapter
from .budget import Dims
from .conductor import Conductor
from .reporting import report_to_json
from .types import Epoch, TaskGraph


class LocalCommandPermissionError(PermissionError):
    """Raised when command execution is requested without explicit operator consent."""


def run_local_graph(
    graph: TaskGraph,
    *,
    allow_local_commands: bool,
    reviewer: str = "agy",
    closer: str = "agy",
) -> dict[str, Any]:
    """Run a TaskGraph locally through the conductor and return stable JSON evidence."""
    if any(node.command for node in graph.nodes) and not allow_local_commands:
        raise LocalCommandPermissionError("local command execution requires --allow-local-commands")

    adapter = ScriptedAdapter(
        {
            node.id: CannedResult()
            for node in graph.nodes
            if node.role not in ("test", "verify", "reviewer", "closer")
        }
    )
    conductor = Conductor(
        graph,
        adapter,
        limit=Dims(tokens=10_000, usd=10.0),
        epoch=Epoch(epoch_seq=1, epoch_id="local-runner"),
        reviewer=reviewer,
        closer=closer,
    )
    return report_to_json(conductor.run())
