from __future__ import annotations

from scripts.phase5_d5_1_benchmark_probe import run_probe


def test_phase5_benchmark_probe_records_current_repo_manifest_and_blinding():
    result = run_probe(write_output=False)

    assert result["gate"] == "D5.1/benchmark-manifest"
    assert result["passed"] is True
    assert result["manifest"]["pinned"] is True
    assert result["run_record"]["valid"] is True
    assert result["run_record"]["task_count"] == 4
    assert result["run_record"]["missing_per_item_arm_maps"] == []
    assert result["judge_packet"]["provider_labels_stripped"] is True
