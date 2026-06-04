"""The conductor — the thin deterministic spine that runs a TaskGraph to terminal state.

The conductor owns no expensive thinking; it composes the already-built primitives — the
§D.1 ``Scheduler`` (ready-set + state machine + FR-5.1 skip), the §D.4 ``BudgetLedger``
(reserve→commit), the FR-7 ``Checkpoint`` (epoch-validated journal), and an adapter
(``scripted`` in Phase 1) — into three execution shapes:

* **``agent(node)``** — the atom. Computes the node's ``idempotency_key`` at ready-time
  (§D.1 [H4], folding resolved input digests), serves it from the FR-7 cache on resume
  (releasing any orphan reservation, FR-30.1), else dispatches a reserve→run→classify→
  commit→journal retry loop. Schema/transport/timeout/tool failures (``Transient``) retry
  within ``max_schema_retries`` and the cumulative budget; ``Deterministic``/``Budget``
  failures are terminal (§D.2).
* **``run()``** — the barrier driver. Dispatches each ready batch (back-pressured to
  ``cap``), joins, commits succeeded results, skips the transitive dependents of any
  failed node (FR-5.1), checkpoints the barrier (FR-7), and stops scheduling with a
  best-so-far report when the budget is exhausted (FR-6.6 bounded-overrun).
* **``pipeline(items, stages)``** — per-item staged flow with per-stage journaling (FR-7
  no-barrier cadence): items keep input order, one failing item is isolated with a
  blocker (the others continue), and a resumed item re-runs only from its first
  uncommitted stage.

Phase 1 is synchronous over the zero-token ``scripted`` substrate (FR-17); concurrency is
modelled by cap-bounded sequential batch dispatch, which preserves the FR-5 ready-set and
barrier semantics. Async/live adapters are a later-phase concern.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .budget import BudgetLedger, Dims
from .canonical import canonical, sha256_hex
from .checkpoint import Checkpoint, JournalEntry
from .lockfile import Lockfile
from .model_routing import route_model_tier
from .reducers import run_reducer
from .runners import classify_exit, subprocess_runner
from .scheduler import Scheduler
from .types import (
    DriftRecord,
    Epoch,
    ErrorClass,
    FailureClass,
    NodeSpec,
    NodeStatus,
    ResultEnvelope,
    RunStatus,
    TaskGraph,
    compute_idempotency_key,
)
from .validate import check_drift

__all__ = [
    "Conductor",
    "RunReport",
    "PipelineItemResult",
    "classify",
    "retry_eligible",
]


# --- §D.2 failure classification -------------------------------------------

# The total error_class → FailureClass table (§D.2). ``none`` maps to ``None`` so the
# fail-closed branch (a non-succeeded status carrying ``none``) resolves to Deterministic.
_ERROR_TO_FAILURE: dict[ErrorClass, FailureClass | None] = {
    ErrorClass.NONE: None,
    ErrorClass.SCHEMA_INVALID: FailureClass.TRANSIENT,
    ErrorClass.TRANSPORT: FailureClass.TRANSIENT,
    ErrorClass.TIMEOUT: FailureClass.TRANSIENT,
    ErrorClass.TOOL: FailureClass.TRANSIENT,
    ErrorClass.AUTH: FailureClass.DETERMINISTIC,
    ErrorClass.BUDGET: FailureClass.BUDGET,
    ErrorClass.UNKNOWN: FailureClass.DETERMINISTIC,
}


def classify(envelope: ResultEnvelope) -> FailureClass | None:
    """Derive the §D.2 ``FailureClass`` (retry verdict) from a result envelope.

    ``null`` iff ``status==succeeded``. A worker/orchestrator-set ``failure_class`` takes
    precedence; an orchestrator ``timed_out`` kill is ``Transient``; otherwise the total
    ``error_class`` table applies, with the fail-closed default (a failed status carrying
    ``none``/``unknown``) resolving to ``Deterministic`` — never retryable-by-default.
    """
    if envelope.status == "succeeded":
        return None
    if envelope.failure_class is not None:
        return envelope.failure_class
    if envelope.status == "timed_out":
        return FailureClass.TRANSIENT
    derived = _ERROR_TO_FAILURE.get(envelope.error_class, FailureClass.DETERMINISTIC)
    return derived if derived is not None else FailureClass.DETERMINISTIC


def retry_eligible(
    failure_class: FailureClass | None,
    error_class: ErrorClass,
    remaining_retries: int,
    retryable_error_classes: tuple[str, ...],
) -> bool:
    """The normative §D.2 retry predicate (budget admission is checked separately).

    ``running→ready`` iff ``failure_class==Transient`` AND ``remaining_retries>0`` AND the
    envelope's ``error_class`` is in the node's ``retryable_error_classes`` (a per-node
    *narrowing* of the Transient set — it can only subtract, never promote).
    """
    return (
        failure_class == FailureClass.TRANSIENT
        and remaining_retries > 0
        and error_class in retryable_error_classes
    )


# --- run + pipeline result shapes ------------------------------------------


@dataclass
class RunReport:
    """A run's terminal summary (§D.7-adjacent). Byte-stable over the scripted substrate."""

    status: RunStatus
    results: dict[str, ResultEnvelope]
    states: dict[str, NodeStatus]
    blockers: list[dict[str, str]]
    spent_tokens: int
    spent_usd: float
    drift_records: list[DriftRecord] = field(default_factory=list)


@dataclass
class PipelineItemResult:
    """One pipeline item's outcome (FR-7 per-item cadence; FR-5.1-analog isolation)."""

    item: Any
    status: str
    envelope: ResultEnvelope | None
    stages_completed: int
    blocker: dict[str, str] | None = None


# --- small dim helpers ------------------------------------------------------


def _dims(consumed: dict[str, Any]) -> Dims:
    return Dims(tokens=int(consumed.get("tokens", 0)), usd=float(consumed.get("usd", 0.0)))


def _billable(token_usage: dict[str, Any]) -> int:
    # thinking billed as output (§D.4 cost-ledger rule); input is not part of est()'s caps.
    return int(token_usage.get("output", 0)) + int(token_usage.get("thinking", 0))


def _add_consumed(consumed: dict[str, Any], actual: Dims) -> dict[str, Any]:
    return {
        "tokens": int(consumed.get("tokens", 0)) + actual.tokens,
        "usd": float(consumed.get("usd", 0.0)) + actual.usd,
    }


# --- the conductor ----------------------------------------------------------


class Conductor:
    """Runs one ``TaskGraph`` over one adapter to terminal state (FR-5/FR-6/FR-7)."""

    def __init__(
        self,
        graph: TaskGraph,
        adapter: Any,
        *,
        limit: Dims,
        epoch: Epoch,
        checkpoint: Checkpoint | None = None,
        cap: int = 1,
        tool_registry: dict[str, Any] | None = None,
        reducer_registry: dict[str, Any] | None = None,
        fallback_adapter: Any | None = None,
        command_runner: Callable[[list[str]], Any] | None = None,
        opaque_multiplier: int = 1,
        lockfile: Lockfile | None = None,
        resolved_lockfile: Lockfile | None = None,
        allow_drift: bool = False,
        reviewer: str = "agy",
        closer: str = "agy",
    ) -> None:
        self.graph = graph
        self.adapter = adapter
        self.epoch = epoch
        self.checkpoint = checkpoint
        self.cap = max(1, cap)
        self.tool_registry = tool_registry or {}
        self.reducer_registry = reducer_registry or {}
        self.fallback_adapter = fallback_adapter
        self.events: list[dict[str, Any]] = []
        self.command_runner = command_runner or subprocess_runner
        self.ledger = BudgetLedger(limit, opaque_multiplier=opaque_multiplier)
        self.scheduler = Scheduler(graph)
        self.runtime = self.scheduler.states
        self._by_id = {n.id: n for n in graph.nodes}
        self.results: dict[str, ResultEnvelope] = {}
        self.blockers: list[dict[str, str]] = []
        self._budget_stopped = False
        self.lockfile = lockfile
        self.resolved_lockfile = resolved_lockfile
        self.allow_drift = allow_drift
        self.reviewer = reviewer
        self.closer = closer
        self._drift_records: list[DriftRecord] = []

    # --- barrier driver (FR-5/FR-5.1/FR-6.6/FR-7) --------------------------

    def run(self) -> RunReport:
        """Drive the graph to terminal state, checkpointing after each barrier."""
        self._check_drift()
        while not self.scheduler.is_done():
            ready = self.scheduler.ready_set()
            if not ready:
                break
            batch = ready[: self.cap]  # FR-5/CON-8 back-pressure
            for node_id in batch:
                self.agent(self._by_id[node_id])
                if self._budget_stopped:
                    break
            # FR-5.1: join, then skip the transitive dependents of any failed node.
            for node_id in batch:
                if self.runtime[node_id].status == NodeStatus.FAILED:
                    for skipped_id in self.scheduler.propagate_skips(node_id):
                        self._add_blocker(
                            skipped_id, "skipped: upstream dependency failed", node_id
                        )
            self._checkpoint_barrier(batch)  # FR-7 checkpoint-after-barrier
            if self._budget_stopped:  # FR-6.6 best-so-far
                break
        return self._build_report()

    def _check_drift(self) -> None:
        """AC-31: verify lockfile drift before any node runs (§D.5).

        With both the locked and resolved lockfiles supplied, ``check_drift`` records every
        per-key mismatch and — absent ``allow_drift`` — raises ``ValidationError`` on
        control-flow drift (model_pins/prompt_hashes), aborting before dispatch. Absent
        either lockfile, drift checking is skipped (a no-op for pre-built-graph runs).
        """
        if self.lockfile is None or self.resolved_lockfile is None:
            return
        self._drift_records = check_drift(
            self.lockfile, self.resolved_lockfile, allow_drift=self.allow_drift
        )

    # --- the atom (FR-7 cache + FR-6 reserve/commit + §D.2 classify) -------

    def agent(self, node: NodeSpec) -> ResultEnvelope | None:
        """Run a single node to terminal state (or serve it from cache); ``None`` if the
        budget is exhausted before it can be dispatched (best-so-far stop)."""
        runtime = self.runtime[node.id]
        # 1. ready-time idempotency_key (§D.1 [H4]) — folds resolved input digests.
        node.idempotency_key = compute_idempotency_key(
            node, self._resolve_inputs(node), self.tool_registry
        )
        # 2. resume: restore monotonic runtime (same key only), then FR-7 cache-hit.
        self._restore_runtime(node, runtime)
        cached = self._serve_from_cache(node, runtime)
        if cached is not None:
            return cached
        # 3. dispatch with the reserve→run→classify→commit retry loop.
        return self._dispatch(node, runtime)

    def _dispatch(self, node: NodeSpec, runtime: Any) -> ResultEnvelope | None:
        self.scheduler.mark(node.id, NodeStatus.READY)
        admission = self._reserve(node, runtime)
        if not admission.admitted:  # global/subtree budget gone before first run
            self._budget_stopped = True
            self._add_blocker(
                node.id, "budget exhausted before dispatch", admission.reason or "global"
            )
            return None
        while True:
            self.scheduler.mark(node.id, NodeStatus.RESERVED)
            runtime.reservation_id = admission.reservation_id
            self.scheduler.mark(node.id, NodeStatus.RUNNING)
            runtime.attempt += 1
            envelope = self._run_node(node, runtime, reservation_id=admission.reservation_id)
            self._stamp(envelope, node, runtime)
            actual = Dims(tokens=_billable(envelope.token_usage), usd=float(envelope.cost_usd))
            accounting = self.adapter.accounting
            if self.fallback_adapter is not None and envelope.adapter == self.fallback_adapter.name:
                accounting = self.fallback_adapter.accounting
            self.ledger.commit(self.epoch.epoch_seq, node.id, actual, accounting=accounting)
            runtime.budget_consumed = _add_consumed(runtime.budget_consumed, actual)
            if node.role in ("reviewer", "closer") and actual.tokens > 1000:
                self.events.append(
                    {
                        "type": "review_budget_alert",
                        "node_id": node.id,
                        "role": node.role,
                        "spent_tokens": actual.tokens,
                        "threshold": 1000,
                        "warning": (
                            f"Review role node '{node.id}' exceeded lightweight token guardrail "
                            f"threshold (1000 tokens) with {actual.tokens} tokens."
                        ),
                    }
                )
                if node.role == "reviewer" and self.closer in ("agy", "codex"):
                    new_closer = "codex" if self.closer == "agy" else "off"
                    self.events.append(
                        {
                            "type": "review_auto_triage",
                            "node_id": node.id,
                            "action": "downgrade_closer",
                            "previous_closer": self.closer,
                            "new_closer": new_closer,
                            "warning": (
                                f"Reviewer node '{node.id}' exceeded budget threshold. Closer adapter "
                                f"downgraded from '{self.closer}' to '{new_closer}' to conserve remaining budget."
                            ),
                        }
                    )
                    self.closer = new_closer
            runtime.error_class = envelope.error_class
            failure_class = classify(envelope)
            if failure_class is None:
                self.scheduler.mark(node.id, NodeStatus.SUCCEEDED)
                self.results[node.id] = envelope
                return envelope
            if retry_eligible(
                failure_class,
                envelope.error_class,
                runtime.remaining_schema_retries,
                node.retry_policy.retryable_error_classes,
            ):
                retry_admission = self._reserve(node, runtime)  # cumulative budget gate
                if retry_admission.admitted:
                    runtime.remaining_schema_retries -= 1
                    admission = retry_admission
                    self.scheduler.mark(node.id, NodeStatus.READY)  # running→ready
                    continue
            # FR-35: a Deterministic primary failure (not Budget, not an exhausted
            # Transient) earns ONE capability- and budget-gated fallback attempt,
            # recorded as a model_switch. A succeeding switch flips the node to
            # succeeded; anything else falls through to the terminal failure below.
            if failure_class == FailureClass.DETERMINISTIC or (
                node.role in ("reviewer", "closer") and failure_class != FailureClass.BUDGET
            ):
                fb_envelope = self._fallback_attempt(node, runtime, envelope)
                if fb_envelope is not None:
                    envelope = fb_envelope
                    if classify(envelope) is None:
                        self.scheduler.mark(node.id, NodeStatus.SUCCEEDED)
                        self.results[node.id] = envelope
                        return envelope
            # terminal failure: Deterministic/Budget, retries exhausted, or retry unfunded.
            self.scheduler.mark(node.id, NodeStatus.FAILED)
            self.results[node.id] = envelope
            self._add_blocker(node.id, "node failed", envelope.error_class.value)
            return envelope

    def _run_node(self, node: NodeSpec, runtime: Any, *, reservation_id: Any) -> ResultEnvelope:
        """One attempt's envelope: a reducer node merges its committed child artifacts in
        code (§D.3 — node-id-sorted, double-executed for purity); every other role
        dispatches to the worker adapter. Reducer output is zero-token, so it flows through
        the same reserve->commit->classify->journal path as any node."""
        if node.role == "reducer" and node.reducer is not None:
            children = [
                {"node_id": dep_id, "artifact": self.results[dep_id].artifact}
                for dep_id in node.dependencies
                if dep_id in self.results and self.results[dep_id].status == "succeeded"
            ]
            merged = run_reducer(node.reducer, children, registry=self.reducer_registry)
            return ResultEnvelope(
                node_id=node.id,
                idempotency_key=node.idempotency_key,
                status="succeeded",
                error_class=ErrorClass.NONE,
                artifact=merged.artifact,
                concerns=merged.concerns,
                token_usage={
                    "input": 0,
                    "thinking": 0,
                    "output": 0,
                    "cached": 0,
                    "accounting": "exact",
                },
            )
        if node.role in ("test", "verify"):
            # FR-34: a test/verify node runs its declared command via the injected runner
            # (not the worker adapter). Nonzero exit ⇒ failed; the code is classified by
            # classify_exit (AC-38/D-5: a clean nonzero is TOOL, a signal-kill's negative
            # code is TIMEOUT) — both →Transient, so it is retried only if policy opts in and
            # is NEVER model-fallback'd (a failing test is a verification result, not a model
            # failure). Exit code → artifact, stdout/stderr → stdout_ref (§D.2); dependents
            # transitively skip (FR-5.1).
            outcome = self.command_runner(node.command or [])
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

        active_adapter = self.adapter
        if node.role not in ("reducer", "test", "verify"):
            entry = self.ledger.entries.get((self.epoch.epoch_seq, node.id))
            reserved_dims = entry.reserved if entry is not None else Dims()
            remaining_budget = self.ledger.available + reserved_dims
            high_value = getattr(node, "high_value", False) or getattr(
                self.graph, "high_value", False
            )
            decision = route_model_tier(
                node,
                failed_attempts=runtime.attempt,
                high_value=high_value,
                remaining_budget=remaining_budget,
            )
            if decision.escalated and self.fallback_adapter is not None:
                if self.fallback_adapter.covers(node.required_capabilities):
                    active_adapter = self.fallback_adapter
                    self.events.append(
                        {
                            "type": "model_switch",
                            "node_id": node.id,
                            "from": getattr(self.adapter, "name", "primary"),
                            "to": getattr(self.fallback_adapter, "name", "fallback"),
                            "error_class": runtime.error_class.value
                            if hasattr(runtime, "error_class")
                            else "none",
                        }
                    )
                else:
                    self._add_blocker(
                        node.id, "fallback misses required capabilities", "fallback_uncovered"
                    )

        if node.role in ("reviewer", "closer"):
            from .hybrid_review import route_review_role

            adapter_name = self.reviewer if node.role == "reviewer" else self.closer
            route = route_review_role(node.role, adapter=adapter_name)
            if route.adapter == "agy":
                try:
                    return active_adapter.run(
                        node, attempt=runtime.attempt, reservation_id=reservation_id
                    )
                except Exception as exc:
                    return ResultEnvelope(
                        node_id=node.id,
                        idempotency_key=node.idempotency_key,
                        status="failed",
                        error_class=ErrorClass.UNKNOWN,
                        artifact={"crash": type(exc).__name__},
                        stdout_ref=f"{type(exc).__name__}: {exc}",
                        token_usage={
                            "input": 0,
                            "thinking": 0,
                            "output": 0,
                            "cached": 0,
                            "accounting": "exact",
                        },
                    )
            elif route.adapter == "claude":
                from .adapters.claude import ClaudeAdapter

                try:
                    return ClaudeAdapter().run(
                        node, attempt=runtime.attempt, reservation_id=reservation_id
                    )
                except Exception as exc:
                    return ResultEnvelope(
                        node_id=node.id,
                        idempotency_key=node.idempotency_key,
                        status="failed",
                        error_class=ErrorClass.UNKNOWN,
                        artifact={"crash": type(exc).__name__},
                        stdout_ref=f"{type(exc).__name__}: {exc}",
                        token_usage={
                            "input": 0,
                            "thinking": 0,
                            "output": 0,
                            "cached": 0,
                            "accounting": "exact",
                        },
                    )
            elif route.adapter == "codex":
                from .adapters.codex import CodexAdapter

                try:
                    return CodexAdapter().run(
                        node, attempt=runtime.attempt, reservation_id=reservation_id
                    )
                except Exception as exc:
                    return ResultEnvelope(
                        node_id=node.id,
                        idempotency_key=node.idempotency_key,
                        status="failed",
                        error_class=ErrorClass.UNKNOWN,
                        artifact={"crash": type(exc).__name__},
                        stdout_ref=f"{type(exc).__name__}: {exc}",
                        token_usage={
                            "input": 0,
                            "thinking": 0,
                            "output": 0,
                            "cached": 0,
                            "accounting": "exact",
                        },
                    )
            return ResultEnvelope(
                node_id=node.id,
                idempotency_key=node.idempotency_key,
                status="succeeded",
                error_class=ErrorClass.NONE,
                artifact={
                    "route": route.to_json(),
                    "commands_executed": False,
                },
                token_usage={
                    "input": 0,
                    "thinking": 0,
                    "output": 0,
                    "cached": 0,
                    "accounting": "exact",
                },
            )

        # AC-38/NFR-8 containment: a worker adapter that RAISES is caught and turned into a
        # failed envelope rather than propagated — a crashing worker must never take down the
        # conductor. The crash is opaque (no exit code, no envelope) ⇒ UNKNOWN → Deterministic
        # (§D.2 fail-closed); the exception is surfaced via stdout_ref for the blocker.
        # OS-level isolation (FR-12 worktree / NFR-8 hermetic FS) is Phase-2 — this is the
        # in-process containment seam. KeyboardInterrupt/SystemExit (BaseException) propagate.
        try:
            return active_adapter.run(node, attempt=runtime.attempt, reservation_id=reservation_id)
        except Exception as exc:
            return ResultEnvelope(
                node_id=node.id,
                idempotency_key=node.idempotency_key,
                status="failed",
                error_class=ErrorClass.UNKNOWN,
                artifact={"crash": type(exc).__name__},
                stdout_ref=f"{type(exc).__name__}: {exc}",
                token_usage={
                    "input": 0,
                    "thinking": 0,
                    "output": 0,
                    "cached": 0,
                    "accounting": "exact",
                },
            )

    def _reserve(self, node: NodeSpec, runtime: Any) -> Any:
        accounting = self.adapter.accounting
        if self.fallback_adapter is not None and node.role not in ("reducer", "test", "verify"):
            entry = self.ledger.entries.get((self.epoch.epoch_seq, node.id))
            reserved_dims = entry.reserved if entry is not None else Dims()
            remaining_budget = self.ledger.available + reserved_dims
            high_value = getattr(node, "high_value", False) or getattr(
                self.graph, "high_value", False
            )
            decision = route_model_tier(
                node,
                failed_attempts=runtime.attempt + 1,
                high_value=high_value,
                remaining_budget=remaining_budget,
            )
            if decision.escalated and self.fallback_adapter.covers(node.required_capabilities):
                accounting = self.fallback_adapter.accounting

        return self.ledger.reserve(
            self.epoch.epoch_seq,
            node.id,
            node,
            epoch_id=self.epoch.epoch_id,
            budget_consumed=_dims(runtime.budget_consumed),
            accounting=accounting,
        )

    def _fallback_attempt(
        self, node: NodeSpec, runtime: Any, primary: ResultEnvelope
    ) -> ResultEnvelope | None:
        """FR-35 / AC-35: one capability- and budget-gated dispatch on the configured
        fallback adapter after a Deterministic primary failure. Returns the fallback's
        (stamped + committed) envelope, or ``None`` when no fallback fired. A missing
        fallback is a silent no-op (the node fails normally — AC-1 unperturbed); an
        uncovered fallback (FR-13) raises a ``fallback_uncovered`` blocker and fires
        nothing; an unfunded re-reserve (FR-6) raises a budget blocker and fires nothing. A
        fallback never consumes a transient schema-retry. A dispatched switch is appended to
        the event log as a ``model_switch`` (ARCHITECTURE §5.5).
        """
        if node.role in ("reviewer", "closer"):
            current_adapter = self.reviewer if node.role == "reviewer" else self.closer
            if current_adapter == "agy":
                new_adapter = "codex"
            elif current_adapter == "codex":
                new_adapter = "off"
            else:
                return None

            admission = self.ledger.reserve(
                self.epoch.epoch_seq,
                node.id,
                node,
                epoch_id=self.epoch.epoch_id,
                budget_consumed=_dims(runtime.budget_consumed),
                accounting="exact",
            )
            if not admission.admitted:
                self._add_blocker(
                    node.id, "budget exhausted before fallback", admission.reason or "global"
                )
                return None

            self.events.append(
                {
                    "type": "model_switch",
                    "node_id": node.id,
                    "from": current_adapter,
                    "to": new_adapter,
                    "error_class": primary.error_class.value,
                }
            )

            if node.role == "reviewer":
                self.reviewer = new_adapter
            else:
                self.closer = new_adapter

            runtime.attempt += 1
            runtime.reservation_id = admission.reservation_id
            envelope = self._run_node(node, runtime, reservation_id=admission.reservation_id)
            self._stamp(envelope, node, runtime)
            actual = Dims(tokens=_billable(envelope.token_usage), usd=float(envelope.cost_usd))
            self.ledger.commit(
                self.epoch.epoch_seq,
                node.id,
                actual,
                accounting="exact",
            )
            runtime.budget_consumed = _add_consumed(runtime.budget_consumed, actual)
            if node.role in ("reviewer", "closer") and actual.tokens > 1000:
                self.events.append(
                    {
                        "type": "review_budget_alert",
                        "node_id": node.id,
                        "role": node.role,
                        "spent_tokens": actual.tokens,
                        "threshold": 1000,
                        "warning": (
                            f"Review role node '{node.id}' exceeded lightweight token guardrail "
                            f"threshold (1000 tokens) with {actual.tokens} tokens."
                        ),
                    }
                )
                if node.role == "reviewer" and self.closer in ("agy", "codex"):
                    new_closer = "codex" if self.closer == "agy" else "off"
                    self.events.append(
                        {
                            "type": "review_auto_triage",
                            "node_id": node.id,
                            "action": "downgrade_closer",
                            "previous_closer": self.closer,
                            "new_closer": new_closer,
                            "warning": (
                                f"Reviewer node '{node.id}' exceeded budget threshold. Closer adapter "
                                f"downgraded from '{self.closer}' to '{new_closer}' to conserve remaining budget."
                            ),
                        }
                    )
                    self.closer = new_closer
            runtime.error_class = envelope.error_class
            return envelope

        if self.fallback_adapter is None:
            return None
        if not self.fallback_adapter.covers(node.required_capabilities):
            self._add_blocker(
                node.id, "fallback misses required capabilities", "fallback_uncovered"
            )
            return None
        admission = self.ledger.reserve(
            self.epoch.epoch_seq,
            node.id,
            node,
            epoch_id=self.epoch.epoch_id,
            budget_consumed=_dims(runtime.budget_consumed),
            accounting=self.fallback_adapter.accounting,
        )
        if not admission.admitted:
            self._add_blocker(
                node.id, "budget exhausted before fallback", admission.reason or "global"
            )
            return None
        self.events.append(
            {
                "type": "model_switch",
                "node_id": node.id,
                "from": getattr(self.adapter, "name", "primary"),
                "to": getattr(self.fallback_adapter, "name", "fallback"),
                "error_class": primary.error_class.value,
            }
        )
        runtime.attempt += 1
        runtime.reservation_id = admission.reservation_id
        envelope = self.fallback_adapter.run(
            node, attempt=runtime.attempt, reservation_id=admission.reservation_id
        )
        self._stamp(envelope, node, runtime)
        actual = Dims(tokens=_billable(envelope.token_usage), usd=float(envelope.cost_usd))
        self.ledger.commit(
            self.epoch.epoch_seq,
            node.id,
            actual,
            accounting=self.fallback_adapter.accounting,
        )
        runtime.budget_consumed = _add_consumed(runtime.budget_consumed, actual)
        if node.role in ("reviewer", "closer") and actual.tokens > 1000:
            self.events.append(
                {
                    "type": "review_budget_alert",
                    "node_id": node.id,
                    "role": node.role,
                    "spent_tokens": actual.tokens,
                    "threshold": 1000,
                    "warning": (
                        f"Review role node '{node.id}' exceeded lightweight token guardrail "
                        f"threshold (1000 tokens) with {actual.tokens} tokens."
                    ),
                }
            )
            if node.role == "reviewer" and self.closer in ("agy", "codex"):
                new_closer = "codex" if self.closer == "agy" else "off"
                self.events.append(
                    {
                        "type": "review_auto_triage",
                        "node_id": node.id,
                        "action": "downgrade_closer",
                        "previous_closer": self.closer,
                        "new_closer": new_closer,
                        "warning": (
                            f"Reviewer node '{node.id}' exceeded budget threshold. Closer adapter "
                            f"downgraded from '{self.closer}' to '{new_closer}' to conserve remaining budget."
                        ),
                    }
                )
                self.closer = new_closer
        runtime.error_class = envelope.error_class
        return envelope

    # --- resume helpers (FR-7 / FR-30.1 / cross-resume monotonicity) -------

    def _restore_runtime(self, node: NodeSpec, runtime: Any) -> None:
        """Seed runtime from the persisted journal when the node is content-identical.

        A matching ``idempotency_key`` means the same node ran before, so its monotonic
        ``budget_consumed`` / ``remaining_schema_retries`` / ``attempt`` carry forward
        (never reset to zero — AC-1 monotonicity). A changed key (replan edit) or a fresh
        node seeds a clean attempt with the policy's full retry budget.
        """
        persisted = self.checkpoint.get_runtime(node.id) if self.checkpoint is not None else None
        if persisted is not None and persisted.idempotency_key == node.idempotency_key:
            runtime.budget_consumed = dict(persisted.budget_consumed)
            runtime.remaining_schema_retries = persisted.remaining_schema_retries
            runtime.attempt = persisted.attempt
        else:
            runtime.budget_consumed = {"tokens": 0, "usd": 0.0}
            runtime.remaining_schema_retries = node.retry_policy.max_schema_retries
            runtime.attempt = 0

    def _serve_from_cache(self, node: NodeSpec, runtime: Any) -> ResultEnvelope | None:
        """FR-7 cache-hit: adopt a committed-terminal journaled result without re-running."""
        if self.checkpoint is None:
            return None
        hit = self.checkpoint.lookup(node.idempotency_key)  # epoch-gated cache
        if hit is None or hit.envelope is None:
            return None
        if hit.status not in (NodeStatus.SUCCEEDED.value, NodeStatus.FAILED.value):
            return None
        # FR-30.1: release any open reservation before emitting node-succeeded (no phantom).
        self.ledger.release(self.epoch.epoch_seq, node.id)
        runtime.status = NodeStatus(hit.status)  # resume restore, not a live §D.1 edge
        runtime.attempt = hit.attempt
        runtime.remaining_schema_retries = hit.remaining_schema_retries
        runtime.budget_consumed = dict(hit.budget_consumed)
        runtime.error_class = hit.envelope.error_class
        self.results[node.id] = hit.envelope
        if hit.status == NodeStatus.FAILED.value:
            self._add_blocker(node.id, "node failed (cached)", hit.envelope.error_class.value)
        return hit.envelope

    # --- checkpoint + report ------------------------------------------------

    def _checkpoint_barrier(self, batch: list[str]) -> None:
        if self.checkpoint is None:
            return
        entries: list[JournalEntry] = []
        for node_id in batch:
            runtime = self.runtime[node_id]
            envelope = self.results.get(node_id)
            if envelope is None or runtime.status not in (
                NodeStatus.SUCCEEDED,
                NodeStatus.FAILED,
            ):
                continue  # only committed-terminal nodes are journaled
            entries.append(
                JournalEntry(
                    node_id=node_id,
                    idempotency_key=self._by_id[node_id].idempotency_key,
                    epoch_id=self.epoch.epoch_id,
                    epoch_seq=self.epoch.epoch_seq,
                    status=runtime.status.value,
                    attempt=runtime.attempt,
                    remaining_schema_retries=runtime.remaining_schema_retries,
                    budget_consumed=dict(runtime.budget_consumed),
                    envelope=envelope,
                )
            )
        if entries:
            self.checkpoint.commit_barrier(entries)

    def _build_report(self) -> RunReport:
        states = {node_id: self.runtime[node_id].status for node_id in self._by_id}
        all_succeeded = all(s == NodeStatus.SUCCEEDED for s in states.values())
        return RunReport(
            status=RunStatus.SUCCEEDED if all_succeeded else RunStatus.FAILED,
            results=dict(self.results),
            states=states,
            blockers=list(self.blockers),
            spent_tokens=self.ledger.spent.tokens,
            spent_usd=self.ledger.spent.usd,
            drift_records=list(self._drift_records),
        )

    # --- shared utilities ---------------------------------------------------

    def _resolve_inputs(self, node: NodeSpec) -> dict[str, Any]:
        """Map each declared input name to a committed dependency artifact (§D.1 [H4])."""
        resolved: dict[str, Any] = {}
        for name in node.inputs:
            for dep_id in node.dependencies:
                dep = self.results.get(dep_id)
                if dep is not None and name in dep.artifact:
                    resolved[name] = dep.artifact[name]
                    break
        return resolved

    def _stamp(self, envelope: ResultEnvelope, node: NodeSpec, runtime: Any) -> None:
        envelope.node_id = node.id
        envelope.idempotency_key = node.idempotency_key
        envelope.attempt = runtime.attempt
        envelope.reservation_id = runtime.reservation_id

    def _add_blocker(self, node_id: str, what: str, needs: str) -> None:
        self.blockers.append({"id": node_id, "what": what, "needs": needs})

    # --- pipeline() : per-item staged flow (FR-7 per-item cadence) ---------

    def pipeline(
        self,
        items: list[Any],
        stages: list[Callable[[Any, dict[str, Any] | None], ResultEnvelope]],
        *,
        pipeline_id: str = "pipe",
    ) -> list[PipelineItemResult]:
        """Stream ``items`` through ``stages`` independently, journaling each completed
        stage. Items keep input order; a failing stage isolates only its item (FR-5.1
        analog); a resumed item re-runs from its first uncommitted stage (FR-7)."""
        return [
            self._run_pipeline_item(pipeline_id, index, item, stages)
            for index, item in enumerate(items)
        ]

    def _run_pipeline_item(
        self,
        pipeline_id: str,
        index: int,
        item: Any,
        stages: list[Callable[[Any, dict[str, Any] | None], ResultEnvelope]],
    ) -> PipelineItemResult:
        prev: dict[str, Any] | None = None
        completed = 0
        final_env: ResultEnvelope | None = None
        for stage_idx, stage in enumerate(stages):
            key = self._pipeline_key(pipeline_id, index, stage_idx, len(stages))
            cached = self._pipeline_cache_lookup(key)
            if cached is not None:  # stage already committed pre-crash → skip (FR-7)
                final_env, prev, completed = cached, cached.artifact, completed + 1
                continue
            envelope = stage(item, prev)
            envelope.node_id = f"{pipeline_id}:{index}:{stage_idx}"
            envelope.idempotency_key = key
            if classify(envelope) is not None:  # this item fails; the others continue
                blocker = {
                    "id": str(item),
                    "what": f"pipeline stage {stage_idx} failed",
                    "needs": envelope.error_class.value,
                }
                self.blockers.append(blocker)
                return PipelineItemResult(
                    item=item,
                    status="failed",
                    envelope=envelope,
                    stages_completed=completed,
                    blocker=blocker,
                )
            final_env, prev, completed = envelope, envelope.artifact, completed + 1
            self._pipeline_journal(key, envelope)
        return PipelineItemResult(
            item=item,
            status="succeeded",
            envelope=final_env,
            stages_completed=completed,
            blocker=None,
        )

    def _pipeline_key(self, pipeline_id: str, index: int, stage_idx: int, n_stages: int) -> str:
        # Folds epoch_id so a checkpoint-epoch bump cold-busts the pipeline cache too.
        return sha256_hex(canonical([pipeline_id, index, stage_idx, n_stages, self.epoch.epoch_id]))

    def _pipeline_cache_lookup(self, key: str) -> ResultEnvelope | None:
        if self.checkpoint is None:
            return None
        hit = self.checkpoint.lookup(key)
        if hit is None or hit.envelope is None or hit.status != NodeStatus.SUCCEEDED.value:
            return None
        return hit.envelope

    def _pipeline_journal(self, key: str, envelope: ResultEnvelope) -> None:
        if self.checkpoint is None:
            return
        self.checkpoint.commit_barrier(
            [
                JournalEntry(
                    node_id=envelope.node_id,
                    idempotency_key=key,
                    epoch_id=self.epoch.epoch_id,
                    epoch_seq=self.epoch.epoch_seq,
                    status=NodeStatus.SUCCEEDED.value,
                    attempt=1,
                    remaining_schema_retries=0,
                    budget_consumed={"tokens": 0, "usd": 0.0},
                    envelope=envelope,
                )
            ]
        )
