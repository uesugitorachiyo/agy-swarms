from __future__ import annotations

from scripts.phase5_d5_3_tokens_probe import run_probe


def test_phase5_tokens_probe_records_m2_token_ledger_evidence():
    result = run_probe(write_output=False)

    assert result["gate"] == "D5.3/m2-token-ledger"
    assert result["passed"] is True
    assert result["m2"]["status"] == "passed"
    assert result["m2"]["billable_equivalent_tokens"] < result["m2"]["threshold_tokens"]
    assert result["m2"]["row_counts_by_kind"]["judge"] == 1
    assert result["m2"]["row_counts_by_kind"]["retry"] == 1
    assert result["m2"]["row_counts_by_kind"]["escalation"] == 1
    assert result["m2"]["reported_only"]["factory_v3_token_baseline"] == ("missing_reported_only")
