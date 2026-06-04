from __future__ import annotations

from scripts.phase5_d5_2_quality_probe import run_probe


def test_phase5_quality_probe_records_m1_evidence():
    result = run_probe(write_output=False)

    assert result["gate"] == "D5.2/m1-quality"
    assert result["passed"] is True
    assert result["m1"]["status"] == "passed"
    assert result["m1"]["ci_lower_bound"] >= result["m1"]["threshold"]
    assert result["m1"]["num_runs"] >= 5
    assert result["m1"]["mean_ratio"] > 0.95

    # Verify judge provenance is recorded
    jc = result["m1"]["judge_config"]
    assert jc["judge_model_id"] == "gemini-3.5-flash"
    assert jc["temperature"] == 0
    assert jc["rubric_hash"]
    assert len(jc["panel_composition"]) >= 1

    # Verify each score has the expected shape
    for score in result["m1"]["scores"]:
        assert "run_id" in score
        assert "candidate_score" in score
        assert "baseline_score" in score
        assert score["ratio"] > 0

    # Verify provenance
    assert result["provenance"]["rubric_hash"]
    assert result["provenance"]["blinding_seed"]
    assert result["provenance"]["temperature"] == 0
