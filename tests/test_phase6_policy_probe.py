from __future__ import annotations

from scripts.phase6_d6_1_policy_probe import run_probe


def test_phase6_policy_probe_records_all_tiered_autonomy_modes():
    result = run_probe(write_output=False)

    assert result["gate"] == "D6.1/policy-engine"
    assert result["passed"] is True
    assert result["policy"]["auto_write"]["status"] == "allowed"
    assert result["policy"]["batched_patch"]["status"] == "queued"
    assert result["policy"]["strict_without_token"]["status"] == "blocked"
    assert result["policy"]["strict_with_token"]["status"] == "allowed"
    assert result["policy"]["unknown_mode_fails_closed"] is True
