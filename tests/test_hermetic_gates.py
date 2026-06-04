"""AC-28 hermetic gate execution."""

import socket

import pytest

from agy_swarms.gates import (
    GateError,
    Verdict,
    declared_network_dependencies,
    run_gate,
)


def test_gate_attempting_undeclared_network_call_is_blocked():
    def _network_gate(output, contract):
        socket.create_connection(("undeclared.example", 443), timeout=0.01)
        return Verdict(passed=True)

    with pytest.raises(GateError, match="undeclared network"):
        run_gate(_network_gate, {}, {}, gate_id="net")


def test_declared_network_dependency_is_explicit_in_contract_and_allowed():
    contract = {
        "network_dependencies": [
            {"host": "declared.example", "port": 443, "purpose": "fixture probe"}
        ]
    }

    def _declared_network_gate(output, contract):
        sock = socket.create_connection(("declared.example", 443), timeout=0.01)
        sock.close()
        return Verdict(passed=True)

    verdict = run_gate(_declared_network_gate, {}, contract, gate_id="declared-net")

    assert verdict.passed is True
    assert declared_network_dependencies(contract) == (("declared.example", 443),)


def test_declared_gate_cannot_call_a_different_network_dependency():
    contract = {
        "network_dependencies": [
            {"host": "declared.example", "port": 443, "purpose": "fixture probe"}
        ]
    }

    def _wrong_network_gate(output, contract):
        socket.create_connection(("other.example", 443), timeout=0.01)
        return Verdict(passed=True)

    with pytest.raises(GateError, match="other.example:443"):
        run_gate(_wrong_network_gate, {}, contract, gate_id="wrong-net")


def test_hermetic_network_guard_preserves_double_execution_purity_check():
    calls = {"n": 0}

    def _flaky_gate(output, contract):
        calls["n"] += 1
        return Verdict(passed=(calls["n"] == 1))

    with pytest.raises(GateError, match="divergent verdict"):
        run_gate(_flaky_gate, {}, {}, gate_id="still-flaky")
