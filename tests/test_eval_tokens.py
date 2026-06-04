"""D5.3 M2 billable-equivalent token ledger."""

import pytest

from agy_swarms.eval.tokens import (
    M2GateStatus,
    TokenLedgerIncomplete,
    TokenLedgerRow,
    TokenRowKind,
    build_token_report,
    parse_cache_multiplier,
)


def test_billable_equivalent_tokens_include_all_required_row_classes():
    report = build_token_report(
        rows=(
            TokenLedgerRow("worker-1", TokenRowKind.WORKER, input_uncached=100, output=50),
            TokenLedgerRow("judge-1", TokenRowKind.JUDGE, input_uncached=20, output=10),
            TokenLedgerRow("retry-1", TokenRowKind.RETRY, input_uncached=10, output=5),
            TokenLedgerRow(
                "optimizer-1", TokenRowKind.OPTIMIZER_REVISION, input_uncached=8, output=4
            ),
            TokenLedgerRow("escalation-1", TokenRowKind.ESCALATION, input_uncached=7, output=3),
            TokenLedgerRow("cache-write-1", TokenRowKind.CACHE_WRITE, input_uncached=30),
            TokenLedgerRow(
                "opaque-calibration-1",
                TokenRowKind.OPAQUE_ADAPTER_CALIBRATION,
                cached_read=10,
            ),
            TokenLedgerRow("tool-io-1", TokenRowKind.TOOL_IO, input_uncached=6, output=2),
        ),
        cache_mult=1.5,
        opus_baseline_billable_tokens=575,
        target_ratio=0.60,
    )

    assert report.status == M2GateStatus.PASSED
    assert report.billable_equivalent_tokens == 270
    assert report.threshold_tokens == 345
    assert report.row_counts_by_kind == {
        "worker": 1,
        "judge": 1,
        "retry": 1,
        "optimizer_revision": 1,
        "escalation": 1,
        "cache_write": 1,
        "opaque_adapter_calibration": 1,
        "tool_io": 1,
    }
    assert report.reported_only["factory_v3_token_baseline"] == "missing_reported_only"


def test_missing_cache_multiplier_is_blocking_incomplete():
    rows = (TokenLedgerRow("worker-1", TokenRowKind.WORKER, input_uncached=1),)

    with pytest.raises(TokenLedgerIncomplete, match="cache_mult"):
        build_token_report(
            rows=rows,
            cache_mult=None,
            opus_baseline_billable_tokens=575,
            target_ratio=0.60,
            required_kinds=(TokenRowKind.WORKER,),
        )


def test_missing_judge_retry_or_escalation_rows_block_m2():
    rows = (
        TokenLedgerRow("worker-1", TokenRowKind.WORKER, input_uncached=10, output=5),
        TokenLedgerRow("retry-1", TokenRowKind.RETRY, input_uncached=2, output=1),
        TokenLedgerRow("escalation-1", TokenRowKind.ESCALATION, input_uncached=2, output=1),
    )

    with pytest.raises(TokenLedgerIncomplete, match="judge"):
        build_token_report(
            rows=rows,
            cache_mult=1.5,
            opus_baseline_billable_tokens=575,
            target_ratio=0.60,
            required_kinds=(
                TokenRowKind.WORKER,
                TokenRowKind.JUDGE,
                TokenRowKind.RETRY,
                TokenRowKind.ESCALATION,
            ),
        )


def test_m2_gate_fails_when_candidate_is_not_below_opus_threshold():
    report = build_token_report(
        rows=(TokenLedgerRow("worker-1", TokenRowKind.WORKER, input_uncached=300, output=45),),
        cache_mult=1.5,
        opus_baseline_billable_tokens=575,
        target_ratio=0.60,
        required_kinds=(TokenRowKind.WORKER,),
    )

    assert report.status == M2GateStatus.FAILED
    assert report.billable_equivalent_tokens == report.threshold_tokens


def test_factory_v3_token_denominator_is_reported_only_when_present():
    report = build_token_report(
        rows=(TokenLedgerRow("worker-1", TokenRowKind.WORKER, input_uncached=1),),
        cache_mult=1.5,
        opus_baseline_billable_tokens=575,
        target_ratio=0.60,
        required_kinds=(TokenRowKind.WORKER,),
        factory_v3_baseline_billable_tokens=10_000,
    )

    assert report.status == M2GateStatus.PASSED
    assert report.reported_only["factory_v3_token_baseline"] == "present_reported_only"
    assert report.reported_only["factory_v3_billable_equivalent_tokens"] == 10_000


def test_cache_multiplier_parser_accepts_phase0_opaque_pin():
    assert parse_cache_multiplier("OPAQUE_1.5_UTF8_BYTES_DIV4_NO_CACHED_READS_G0_8") == 1.5
