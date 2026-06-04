from scripts.phase3_ac3_live_planner_probe import run_probe


def test_live_planner_probe_records_soft_metric_and_instability_concern():
    result = run_probe(write_output=False)

    assert result["gate"] == "AC-3/live-planner-soft"
    assert result["passed"] is True
    assert result["hard_gate"] is False
    assert result["jaccard_threshold"] == 0.70
    assert result["edge_set_jaccard"] < result["jaccard_threshold"]
    assert "planner-instability" in result["concerns"]
    assert result["invariants"]["schema_valid"] is True
    assert result["invariants"]["acyclic"] is True
    assert result["invariants"]["budget_valid"] is True
    assert result["invariants"]["dependency_complete"] is True
    assert result["invariants"]["router_correct"] is True
