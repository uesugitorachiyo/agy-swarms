from scripts.phase4_ac4_exit_probe import run_probe


def test_phase4_exit_probe_aggregates_hard_gates_and_soft_judge_evidence():
    result = run_probe(write_output=False)

    assert result["gate"] == "AC-4/phase4-exit"
    assert result["passed"] is True
    assert result["status"] == "PHASE-4 EXIT READY"
    assert result["hard_failures"] == []

    hard = result["hard_gates"]
    assert hard["verify_loop_terminates"]["passed"] is True
    assert hard["ground_truth_defect_rejected"]["passed"] is True
    assert hard["discovery_loop_terminates"]["passed"] is True
    assert hard["unverified_obligation_blocks"]["passed"] is True
    assert hard["omitted_obligation_caught"]["passed"] is True
    assert hard["false_verification_rejected"]["passed"] is True

    soft = result["soft_evidence"]["judge_only_defect"]
    assert soft["passed"] is True
    assert soft["soft_evidence"]["deterministic_gate"] is False
    assert soft["judge_verdict"]["temperature"] == 0.0
    assert result["soft_concerns"] == ["answer lacks cited evidence"]


def test_phase4_exit_probe_fails_when_a_hard_gate_is_false():
    result = run_probe(
        write_output=False,
        evidence_overrides={
            "ground_truth_verify": {
                "gate": "D4.0/ground-truth-verify",
                "passed": False,
                "planted_defect": {"status": "passed"},
                "fr33_double_execution": {"divergence": False},
            }
        },
    )

    assert result["passed"] is False
    assert result["status"] == "BLOCKED"
    assert result["hard_failures"] == ["ground_truth_defect_rejected"]


def test_phase4_exit_probe_blocks_when_judge_evidence_becomes_deterministic_gate():
    result = run_probe(
        write_output=False,
        evidence_overrides={
            "judge_panel": {
                "gate": "D4.2/judge-panel-soft-evidence",
                "passed": True,
                "judge_verdict": {"temperature": 0.0},
                "soft_evidence": {
                    "deterministic_gate": True,
                    "judge_only_defects": ["answer lacks cited evidence"],
                },
            }
        },
    )

    assert result["passed"] is False
    assert result["status"] == "BLOCKED"
    assert result["hard_failures"] == ["judge_only_evidence_separated"]
