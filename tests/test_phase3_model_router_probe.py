from pathlib import Path

from scripts.phase3_ac3_model_router_probe import run_probe


def test_model_router_probe_records_fixture_and_escalation_evidence():
    result = run_probe(
        router_cases_path=Path("benchmarks/router_cases.json"),
        lockfile_path=Path("agy.lock"),
        write_output=False,
    )

    assert result["gate"] == "AC-3/model-router"
    assert result["passed"] is True
    assert result["fixture"]["accuracy"] == 1.0
    assert result["fixture"]["router_cases_sha_matches_lock"] is True
    assert result["escalation"]["admitted"]["escalated"] is True
    assert result["escalation"]["admitted"]["charge"]["tokens"] > 0
    assert result["escalation"]["blocked"]["budget_admitted"] is False
    assert result["escalation"]["blocked"]["concerns"] == ["escalation_budget_blocked"]
