"""AC-0.5 — in-memory recorded-graph store for byte-identical replay (D-3; FR-3.1/§D.6).

A planner-decomposed ``TaskGraph`` is recorded here keyed by ``(task_sha, context_hash)``
so a re-run with the same key reuses the recorded graph rather than re-decomposing. D-3
keeps this in memory for Phase 1; the SQLite-backed fold into the checkpoint epoch (FR-7)
is a later-phase concern.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .types import TaskGraph

__all__ = ["GraphStore"]

_Key = tuple[str, str]


@dataclass
class GraphStore:
    """Maps ``(task_sha, context_hash)`` → the recorded ``TaskGraph`` (D-3)."""

    _graphs: dict[_Key, TaskGraph] = field(default_factory=dict)

    def get(self, key: _Key) -> TaskGraph | None:
        """Return the recorded graph for ``key``, or ``None`` if none is recorded."""
        return self._graphs.get(key)

    def put(self, key: _Key, graph: TaskGraph) -> None:
        """Record ``graph`` under ``key`` for byte-identical replay."""
        self._graphs[key] = graph
