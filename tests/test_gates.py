"""AC-29 / FR-33 — the gate-purity double-execution harness (Phase-1-exit gate).

A code-owned gate SHALL be a PURE function of ``(output, contract)`` (FR-33): no wall-clock,
no RNG, no ambient network/filesystem reads beyond the declared ``output``+``contract``, no
mutable global state. ``run_gate`` DOUBLE-EXECUTES each gate on identical ``(output,
contract)`` and raises ``GateError`` on a divergent verdict — the enforcement that stops an
impure gate from journaling a ``passed`` that re-verifies as ``failed`` on resume (poisoning
the FR-7 cache), exactly the hazard ``run_reducer`` guards for reducers (§D.3 SPEC:302,
"mirrors FR-33"). ``run_gate_corpus`` is the AC-29 harness: sweep the corpus, report ZERO
divergence, and name the first impure gate (SPEC:481).
"""

import pytest

from agy_swarms.gates import (
    GATES,
    GateCase,
    GateError,
    Verdict,
    run_gate,
    run_gate_corpus,
)


def _eq_gate(output, contract):
    # PURE: the verdict is a function ONLY of (output, contract).
    return Verdict(passed=output.get("value") == contract.get("expected"))


def test_run_gate_returns_a_pure_gates_verdict():
    assert run_gate(_eq_gate, {"value": 5}, {"expected": 5}, gate_id="eq").passed is True
    assert run_gate(_eq_gate, {"value": 5}, {"expected": 6}, gate_id="eq").passed is False


def test_run_gate_catches_a_deterministically_divergent_gate():
    # An impure gate whose verdict differs across the two executions MUST be caught: here a
    # call-counter closure flips ``passed`` on the 2nd call (guaranteed divergence). run_gate
    # double-executes and raises GateError naming the gate — mirrors reducers.run_reducer.
    calls = {"n": 0}

    def _flaky_gate(output, contract):
        calls["n"] += 1
        return Verdict(passed=(calls["n"] % 2 == 1))  # True then False

    with pytest.raises(GateError, match="flaky"):
        run_gate(_flaky_gate, {}, {}, gate_id="flaky")


def test_run_gate_catches_a_wall_clock_reading_gate(monkeypatch):
    # FR-33's LITERAL impurity example: a gate that reads wall-clock. Stub time.time to a
    # strictly-increasing clock so the impurity is DETERMINISTICALLY divergent (no flake);
    # the harness catches it with NO new code — the C2 double-exec/canonical-compare suffices.
    import time

    ticks = iter([100.0, 200.0, 300.0, 400.0])
    monkeypatch.setattr(time, "time", lambda: next(ticks))

    def _clock_gate(output, contract):
        return Verdict(passed=True, defects=(f"checked_at={time.time()}",))

    with pytest.raises(GateError, match="clocky"):
        run_gate(_clock_gate, {}, {}, gate_id="clocky")


def test_run_gate_corpus_passes_a_pure_corpus():
    # The AC-29 sweep: every gate over its corpus double-executes with ZERO divergence and
    # the verdicts come back in corpus order.
    registry = {**GATES, "eq": _eq_gate}
    corpus = [
        GateCase(gate_id="eq", output={"value": 1}, contract={"expected": 1}),
        GateCase(gate_id="eq", output={"value": 1}, contract={"expected": 2}),
    ]
    verdicts = run_gate_corpus(corpus, registry=registry)
    assert [v.passed for v in verdicts] == [True, False]


def test_run_gate_corpus_over_live_registry_reports_zero_divergence():
    # Standing Phase-1-exit guard: the LIVE GATES registry sweeps clean. Phase 1 ships GATES
    # empty, so this is [] today; it stays green (zero divergence) as real gates land.
    corpus = [GateCase(gate_id=gid, output={}, contract={}) for gid in GATES]
    assert run_gate_corpus(corpus) == []  # no registry= → defaults to the live GATES


def test_run_gate_corpus_catches_a_planted_impure_gate_and_names_it():
    # AC-29 verbatim (SPEC:481): a deliberately-impure planted gate in the corpus SHALL be
    # caught (run fails) and the harness SHALL identify the offending gate by id.
    counter = {"n": 0}

    def _impure(output, contract):
        counter["n"] += 1
        return Verdict(passed=(counter["n"] % 2 == 1))

    registry = {"pure": _eq_gate, "planted_impure": _impure}
    corpus = [
        GateCase(gate_id="pure", output={"value": 1}, contract={"expected": 1}),
        GateCase(gate_id="planted_impure", output={}, contract={}),
    ]
    with pytest.raises(GateError, match="planted_impure"):
        run_gate_corpus(corpus, registry=registry)


def test_run_gate_corpus_rejects_an_unknown_gate_id():
    corpus = [GateCase(gate_id="nope", output={}, contract={})]
    with pytest.raises(GateError, match="nope"):
        run_gate_corpus(corpus, registry={})


def test_run_gate_passes_exactly_output_and_contract_both_executions():
    # Lock the (output, contract)-only contract: the gate receives EXACTLY those two args,
    # and the double-execution feeds byte-identical inputs both times (mirrors the reducer
    # byte-identical guard). A gate pure over (output, contract) is therefore deterministic.
    seen = []

    def _spy(output, contract):
        seen.append((dict(output), dict(contract)))
        return Verdict(passed=True)

    run_gate(_spy, {"o": 1}, {"c": 2}, gate_id="spy")
    assert seen == [({"o": 1}, {"c": 2}), ({"o": 1}, {"c": 2})]  # twice, identical inputs
