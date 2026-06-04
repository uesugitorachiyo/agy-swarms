from scripts.phase4_d4_2_judges_probe import run_probe


def test_phase4_judges_probe_records_soft_judge_evidence():
    result = run_probe(write_output=False)

    assert result["gate"] == "D4.2/judge-panel-soft-evidence"
    assert result["passed"] is True
    assert result["same_model_panel"]["accepted"] is False
    assert result["agy_oauth_diverse_panel"]["accepted"] is False
    assert result["diverse_panel"]["accepted"] is True
    assert result["judge_verdict"]["temperature"] == 0.0
    assert result["judge_verdict"]["rubric_sha"] == "sha256:phase4-rubric"
    assert result["soft_evidence"]["deterministic_gate"] is False
    assert result["soft_evidence"]["judge_only_defects"] == ["answer lacks cited evidence"]
