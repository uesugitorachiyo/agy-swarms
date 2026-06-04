from pathlib import Path

from scripts.phase2_d2_9_adr001_go_kill import run_probe


def test_adr001_probe_returns_profile_and_decision():
    result = run_probe(
        reference_task_path=Path("benchmarks/reference_task.md"),
        worker_count=4,
        model_wait_s=0.001,
    )

    assert result["gate"] == "D2.9/ADR-001"
    assert result["passed"] is True
    assert result["profile"]["reference_task_sha"]
    assert result["decision"]["status"] in {
        "accepted_as_no_port",
        "trigger_rust_port",
    }
