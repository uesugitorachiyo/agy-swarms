from __future__ import annotations

from scripts.phase6_ac6_exit_probe import run_exit_probe


def test_phase6_exit_probe_returns_successful_report():
    result = run_exit_probe()

    assert result["gate"] == "AC-6"
    assert result["passed"] is True
    assert result["sandbox_patch_promotion"]["passed"] is True
    assert result["evidence_replay_externalization"]["passed"] is True
    assert result["thin_cli"]["passed"] is True
    assert result["footprint_gate"]["passed"] is True
    assert result["footprint_gate"]["total_loc"] > 0
    assert result["con7_clean_checkout"]["passed"] is True
