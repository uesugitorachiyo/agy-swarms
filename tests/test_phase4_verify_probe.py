from scripts.phase4_d4_0_verify_probe import run_probe


def test_phase4_verify_probe_records_ground_truth_gate_evidence():
    result = run_probe(write_output=False)

    assert result["gate"] == "D4.0/ground-truth-verify"
    assert result["passed"] is True
    assert result["passing_signal"]["status"] == "passed"
    assert result["planted_defect"]["status"] == "failed"
    assert result["planted_defect"]["defect_ids"] == ["test:planted-unit"]
    assert result["fr33_double_execution"]["passed"] is False
    assert result["fr33_double_execution"]["divergence"] is False
