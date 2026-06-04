"""FR-5 scheduler — ready-set, §D.1 state machine, back-pressure, FR-5.1 skip.

The scheduler is the engine's deterministic, synchronous bookkeeping core. It owns four
concerns and nothing else (no I/O, no async, no budget/adapter knowledge — the conductor
composes those):

* **Ready-set (FR-5):** the ``pending`` nodes whose every ``dependency`` has *committed*
  (``status == succeeded``), returned in graph order so dispatch is deterministic (FR-2).
* **State machine (§D.1):** ``can_transition``/``assert_transition`` admit ONLY the nine
  tabled edges; terminal ``{succeeded, failed, skipped, cancelled}`` have no outgoing
  edge. ``mark`` routes every status change through this guard.
* **Back-pressure (FR-5/CON-8/AC-37):** ``select_dispatch`` hands back at most
  ``cap − in_flight`` ready nodes, so in-flight never exceeds the config-derived
  concurrency cap (``min(provider headroom, cores − 2)``, never model-chosen).
* **Barrier-failure disposition (FR-5.1):** ``propagate_skips`` marks the transitive
  dependents of a terminal ``failed`` node ``skipped`` — including still-``pending`` ones
  (so the run cannot stall, AC-37) — while leaving in-flight ``running`` siblings alone
  (no fail-fast cancellation). Skip is a graph operation, not a §D.1 transition.
"""

from __future__ import annotations

from .types import NodeRuntimeState, NodeStatus, TaskGraph

__all__ = [
    "Scheduler",
    "SchedulerError",
    "can_transition",
    "assert_transition",
    "concurrency_cap",
]


class SchedulerError(Exception):
    """Raised on an illegal §D.1 state transition."""


# --- §D.1 status state machine (the exact 9-row table) ---------------------

_LEGAL_TRANSITIONS: dict[NodeStatus, frozenset[NodeStatus]] = {
    NodeStatus.PENDING: frozenset({NodeStatus.READY}),
    NodeStatus.READY: frozenset({NodeStatus.RESERVED, NodeStatus.SKIPPED}),
    NodeStatus.RESERVED: frozenset({NodeStatus.RUNNING, NodeStatus.READY, NodeStatus.SKIPPED}),
    NodeStatus.RUNNING: frozenset(
        {
            NodeStatus.SUCCEEDED,
            NodeStatus.FAILED,
            NodeStatus.READY,
            NodeStatus.CANCELLED,
        }
    ),
    # Terminal set — no outgoing transitions (§D.1).
    NodeStatus.SUCCEEDED: frozenset(),
    NodeStatus.FAILED: frozenset(),
    NodeStatus.SKIPPED: frozenset(),
    NodeStatus.CANCELLED: frozenset(),
}

# Non-terminal states a transitive dependent may sit in when an upstream fails (FR-5.1).
# ``running`` is deliberately excluded: an in-flight sibling is never fail-fast-cancelled.
_SKIPPABLE: frozenset[NodeStatus] = frozenset(
    {NodeStatus.PENDING, NodeStatus.READY, NodeStatus.RESERVED}
)

_TERMINAL: frozenset[NodeStatus] = frozenset(
    {
        NodeStatus.SUCCEEDED,
        NodeStatus.FAILED,
        NodeStatus.SKIPPED,
        NodeStatus.CANCELLED,
    }
)


def can_transition(src: NodeStatus, dst: NodeStatus) -> bool:
    """True iff ``src → dst`` is one of the nine legal §D.1 edges."""
    return dst in _LEGAL_TRANSITIONS.get(src, frozenset())


def assert_transition(src: NodeStatus, dst: NodeStatus) -> None:
    """Raise ``SchedulerError`` unless ``src → dst`` is a legal §D.1 edge."""
    if not can_transition(src, dst):
        raise SchedulerError(f"illegal §D.1 transition {src.value!r} → {dst.value!r}")


# --- CON-8 concurrency cap -------------------------------------------------


def concurrency_cap(provider_headroom: int, cpu_cores: int) -> int:
    """``max(1, min(provider_headroom, cpu_cores − 2))`` (FR-5/CON-8).

    A code/config value, never model-chosen. Floored at 1 so a tiny machine or a
    zero-headroom reading can never produce a zero cap (which would stall the run).
    """
    return max(1, min(provider_headroom, cpu_cores - 2))


# --- the scheduler ---------------------------------------------------------


class Scheduler:
    """Deterministic in-memory state for one ``TaskGraph`` run (FR-5).

    Holds the graph and a per-node ``NodeRuntimeState`` map (defaulted to all-``pending``
    on construction, or supplied for resume). The conductor reads ``ready_set`` /
    ``select_dispatch`` and writes status back through ``mark`` (validated) and
    ``propagate_skips`` (the FR-5.1 graph operation).
    """

    def __init__(
        self,
        graph: TaskGraph,
        states: dict[str, NodeRuntimeState] | None = None,
    ) -> None:
        self.graph = graph
        self._by_id = {n.id: n for n in graph.nodes}
        self.states = states or {n.id: NodeRuntimeState(node_id=n.id) for n in graph.nodes}
        # Reverse adjacency (dep → dependents) for O(E) skip propagation (AC-37 scale).
        self._dependents: dict[str, list[str]] = {n.id: [] for n in graph.nodes}
        for node in graph.nodes:
            for dep in node.dependencies:
                self._dependents.setdefault(dep, []).append(node.id)

    def status(self, node_id: str) -> NodeStatus:
        """Current §D.1 status of ``node_id``."""
        return self.states[node_id].status

    def ready_set(self) -> list[str]:
        """``pending`` nodes whose every dependency has committed (FR-5), in graph order."""
        ready: list[str] = []
        for node in self.graph.nodes:
            if self.states[node.id].status != NodeStatus.PENDING:
                continue
            if all(self.states[dep].status == NodeStatus.SUCCEEDED for dep in node.dependencies):
                ready.append(node.id)
        return ready

    def mark(self, node_id: str, new_status: NodeStatus) -> None:
        """Advance ``node_id`` to ``new_status`` through the §D.1 transition guard."""
        assert_transition(self.states[node_id].status, new_status)
        self.states[node_id].status = new_status

    def select_dispatch(self, cap: int, in_flight: int) -> list[str]:
        """Up to ``cap − in_flight`` ready nodes — the FR-5/CON-8/AC-37 back-pressure gate."""
        slots = max(0, cap - in_flight)
        return self.ready_set()[:slots]

    def propagate_skips(self, failed_id: str) -> list[str]:
        """Mark the transitive dependents of terminal-``failed`` ``failed_id`` ``skipped``.

        FR-5.1: every dependent currently in a non-terminal, non-``running`` state is
        skipped (pending dependents included — otherwise they would stall, AC-37);
        in-flight ``running`` siblings are left to finish (no fail-fast cancellation).
        Returns the ids newly skipped. Idempotent: a node, once skipped, leaves
        ``_SKIPPABLE`` and is neither re-skipped nor re-traversed (terminates on the DAG).
        """
        skipped: list[str] = []
        frontier: list[str] = [failed_id]
        while frontier:
            current = frontier.pop()
            for dependent in self._dependents.get(current, ()):
                if self.states[dependent].status in _SKIPPABLE:
                    self.states[dependent].status = NodeStatus.SKIPPED
                    skipped.append(dependent)
                    frontier.append(dependent)
        return skipped

    def is_done(self) -> bool:
        """True once every node has reached a terminal §D.1 status."""
        return all(state.status in _TERMINAL for state in self.states.values())
