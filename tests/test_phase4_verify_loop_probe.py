from scripts.phase4_d4_1_verify_loop_probe import run_probe


def test_phase4_verify_loop_probe_records_d4_1_termination_evidence():
    result = run_probe(write_output=False)

    assert result["gate"] == "D4.1/evaluator-optimizer-loop"
    assert result["passed"] is True
    assert result["scenarios"]["pass_immediate"]["status"] == "passed"
    assert result["scenarios"]["max_revisions"]["status"] == "max_revisions"
    assert result["scenarios"]["budget_exhaustion"]["status"] == "budget_exhausted"
    assert result["scenarios"]["non_monotonic"]["status"] == "non_monotonic"
    assert result["separate_contexts"]["generator_node_id"] == "generator-node"
    assert result["separate_contexts"]["verifier_node_id"] == "verifier-node"
