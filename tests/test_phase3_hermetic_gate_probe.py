from scripts.phase3_ac28_hermetic_gate_probe import run_probe


def test_hermetic_gate_probe_records_blocked_and_declared_network_cases():
    result = run_probe(write_output=False)

    assert result["gate"] == "AC-28/hermetic-gate"
    assert result["passed"] is True
    assert result["undeclared_network"]["blocked"] is True
    assert "undeclared network" in result["undeclared_network"]["error"]
    assert result["declared_network"]["passed"] is True
    assert result["declared_network"]["dependencies"] == [["declared.example", 443]]
    assert result["purity_guard"]["divergence_caught"] is True
