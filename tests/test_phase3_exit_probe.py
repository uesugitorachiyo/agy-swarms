from scripts.phase3_ac3_exit_probe import run_probe


def test_phase3_exit_probe_aggregates_hard_gates_and_soft_live_evidence():
    result = run_probe(write_output=False)

    assert result["gate"] == "AC-3/phase3-exit"
    assert result["passed"] is True
    assert result["status"] == "PHASE-3 EXIT READY"

    hard = result["hard_gates"]
    assert hard["scripted_graph_equivalence"]["passed"] is True
    assert hard["router_fixture"]["passed"] is True
    assert hard["model_router"]["passed"] is True
    assert hard["hermetic_gate"]["passed"] is True
    assert hard["runtime_subgraph"]["passed"] is True
    assert result["hard_failures"] == []

    live = result["soft_evidence"]["live_planner"]
    assert live["passed"] is True
    assert live["hard_gate"] is False
    assert "planner-instability" in live["concerns"]
    assert "planner-instability" in result["soft_concerns"]


def test_phase3_exit_probe_fails_when_a_hard_gate_is_false():
    result = run_probe(
        write_output=False,
        evidence_overrides={
            "router_fixture": {
                "gate": "AC-3/router-fixture",
                "passed": False,
            }
        },
    )

    assert result["passed"] is False
    assert result["status"] == "BLOCKED"
    assert result["hard_failures"] == ["router_fixture"]
