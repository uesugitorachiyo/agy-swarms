from scripts.phase4_d4_3_discovery_probe import run_probe


def test_phase4_discovery_probe_records_dry_and_cap_evidence():
    result = run_probe(write_output=False)

    assert result["gate"] == "D4.3/loop-until-dry"
    assert result["passed"] is True
    assert result["scenarios"]["dry"]["status"] == "dry"
    assert result["scenarios"]["dry"]["discovered_item_ids"] == ["file:a", "file:b", "file:c"]
    assert result["scenarios"]["max_iterations"]["status"] == "max_iterations"
    assert result["scenarios"]["max_iterations"]["blockers"] == [
        "max iterations reached before dry predicate"
    ]
