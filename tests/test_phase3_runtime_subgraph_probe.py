from scripts.phase3_runtime_subgraph_probe import run_probe


def test_runtime_subgraph_probe_records_merge_and_bounded_replan_evidence():
    result = run_probe(write_output=False)

    assert result["gate"] == "D3.5/runtime-subgraph"
    assert result["passed"] is True
    assert result["validate_then_merge"]["merged_node_ids"] == ["root", "child"]
    assert result["bounded_replan"]["attempts"] == 2
    assert result["bounded_replan"]["merged_node_ids"] == ["root", "fixed"]
    assert result["exhaustion"]["exhausted"] is True
    assert result["exhaustion"]["attempts"] == result["configured_max_replans"]
    assert "missing2" in result["exhaustion"]["last_error"]
