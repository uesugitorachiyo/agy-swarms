"""FR-33 gate-purity harness — the code-owned-gate counterpart of §D.3 reducer purity.

A **code-owned gate** (verify/pass-fail gate, FR-21/FR-23/FR-25) SHALL be a **pure function
of ``(output, contract)``** (FR-33): no wall-clock, no RNG, no ambient network/filesystem
reads beyond the declared ``output``+``contract``, no mutable global state. ``run_gate``
**double-executes** each gate on identical ``(output, contract)`` and **fails the run**
(``GateError``) on a divergent verdict — the enforcement that catches an impure gate before
a journaled ``passed`` re-verifies as ``failed`` on resume and poisons the FR-7 cache (the
same hazard ``reducers.run_reducer`` guards for reducers; SPEC:302 — reducer purity "mirrors
FR-33").

``run_gate_corpus`` is the AC-29 Phase-1-exit harness: it sweeps the live ``GATES`` registry
(and any supplied corpus cases) through ``run_gate``, reports zero divergence, and surfaces
the offending gate id on the first impure gate. ``GATES`` ships **empty** in Phase 1 — the
production gate corpus (FR-21/FR-23/FR-25) is a Phase-2/3/4 deliverable; what Phase 1 ships
is the enforcement *mechanism* plus the planted-impure-gate guard.
"""

from __future__ import annotations

import socket
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any, cast

from .canonical import canonical

__all__ = [
    "Verdict",
    "Gate",
    "GateError",
    "GateCase",
    "declared_network_dependencies",
    "run_gate",
    "run_gate_corpus",
    "GATES",
]


class GateError(Exception):
    """Raised on an unknown/unregistered gate or a non-deterministic verdict (FR-33)."""


Output = Mapping[str, Any]
Contract = Mapping[str, Any]


@dataclass(frozen=True)
class Verdict:
    """A code-owned gate's verdict over ``(output, contract)`` (FR-33).

    ``passed`` is the gate decision; ``defects`` the ordered, deterministic reasons it
    failed. The verdict SHALL be a pure function of ``(output, contract)``; the harness
    compares its FULL §D.0 canonical form across a double-execution, so ANY impure field (a
    smuggled timestamp, an RNG token in ``defects``) is caught — not only a flipped
    ``passed``.
    """

    passed: bool
    defects: tuple[str, ...] = ()


Gate = Callable[[Output, Contract], Verdict]


# The code-owned gate registry. EMPTY in Phase 1 — the production corpus (FR-21/FR-23/FR-25)
# is a Phase-2/3/4 deliverable; Phase 1 ships the enforcement harness + planted-impure guard.
GATES: dict[str, Gate] = {}


def run_gate(
    gate: Gate, output: Output, contract: Contract, *, gate_id: str = "<anonymous>"
) -> Verdict:
    """Run ``gate`` on ``(output, contract)``, DOUBLE-EXECUTING to enforce FR-33 purity.

    Raises ``GateError`` (naming ``gate_id``) if the two verdicts are not byte-identical
    under §D.0 canonicalization — the divergence that proves the gate impure and unusable
    until fixed (mirrors ``reducers.run_reducer``'s double-execution guard, §D.3).
    """
    with _hermetic_network_guard(contract, gate_id=gate_id):
        first = gate(output, contract)
        second = gate(output, contract)
    if canonical(asdict(first)) != canonical(asdict(second)):
        raise GateError(
            f"gate {gate_id!r} is non-deterministic "
            "(divergent verdict under double-execution, FR-33) — unusable until fixed"
        )
    return first


def declared_network_dependencies(contract: Contract) -> tuple[tuple[str, int], ...]:
    """Return explicit ``(host, port)`` network dependencies declared by a gate contract.

    AC-28/CON-11 allows network only when it is explicit in the contract. The accepted
    contract shape is ``{"network_dependencies": [{"host": "...", "port": 443}, ...]}``;
    ``"host:port"`` strings are also accepted for compact fixtures.
    """
    raw = contract.get("network_dependencies", ())
    deps: list[tuple[str, int]] = []
    for item in raw:
        if isinstance(item, str):
            host, sep, port = item.rpartition(":")
            if not sep:
                raise GateError(f"invalid network dependency declaration {item!r}")
            deps.append((host, int(port)))
            continue
        if isinstance(item, Mapping):
            deps.append((str(item["host"]), int(item["port"])))
            continue
        raise GateError(f"invalid network dependency declaration {item!r}")
    return tuple(deps)


@contextmanager
def _hermetic_network_guard(contract: Contract, *, gate_id: str) -> Iterator[None]:
    allowed = set(declared_network_dependencies(contract))
    original_create_connection = socket.create_connection

    def _guarded_create_connection(
        address: Any,
        timeout: float | None = None,
        source_address: Any | None = None,
        *,
        all_errors: bool = False,
    ) -> _FakeSocket:
        host, port = _normalize_address(address)
        if (host, port) not in allowed:
            raise GateError(
                f"gate {gate_id!r} attempted undeclared network call to {host}:{port} "
                "(AC-28/CON-11)"
            )
        return _FakeSocket(host=host, port=port)

    socket.create_connection = cast(Any, _guarded_create_connection)
    try:
        yield
    finally:
        socket.create_connection = original_create_connection


def _normalize_address(address: Any) -> tuple[str, int]:
    host, port = address[:2]
    return str(host), int(port)


@dataclass
class _FakeSocket:
    host: str
    port: int
    closed: bool = False

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> _FakeSocket:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()


@dataclass(frozen=True)
class GateCase:
    """One corpus entry: a gate id + the ``(output, contract)`` to double-execute it on."""

    gate_id: str
    output: Output
    contract: Contract


def run_gate_corpus(
    corpus: Sequence[GateCase], *, registry: Mapping[str, Gate] | None = None
) -> list[Verdict]:
    """AC-29 harness: double-execute every corpus case's gate; FAIL on any divergence.

    Resolves each case's ``gate_id`` against ``registry`` (default the live ``GATES``) and
    runs it through ``run_gate``. Returns the verdicts (corpus order) when the whole corpus
    is pure; raises ``GateError`` naming the first offending gate id on the first divergent
    verdict — the Phase-1-exit "report zero divergence" gate (AC-29, SPEC:481).
    """
    reg = GATES if registry is None else registry
    verdicts: list[Verdict] = []
    for case in corpus:
        try:
            gate = reg[case.gate_id]
        except KeyError:
            raise GateError(f"gate {case.gate_id!r} not in GATES registry") from None
        verdicts.append(run_gate(gate, case.output, case.contract, gate_id=case.gate_id))
    return verdicts
