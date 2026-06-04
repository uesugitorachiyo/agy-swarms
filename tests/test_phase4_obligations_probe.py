from scripts.phase4_d4_4_obligations_probe import run_probe


def test_phase4_obligations_probe_records_ac4_planted_failures():
    result = run_probe(write_output=False)

    assert result["gate"] == "D4.4/obligation-closure"
    assert result["passed"] is True
    assert result["scenarios"]["omitted_obligation"]["closable"] is False
    assert result["scenarios"]["false_verification"]["closable"] is False
    assert result["scenarios"]["valid_closure"]["closable"] is True
    assert result["scenarios"]["handoff"]["closure_status"] == "blocked"
    assert result["scenarios"]["handoff"]["unresolved_concerns"]
