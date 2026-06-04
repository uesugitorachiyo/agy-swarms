#!/usr/bin/env python3
"""Run D5.3 M2 billable-equivalent token ledger evidence."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import asdict
from pathlib import Path

from agy_swarms.eval.tokens import (
    M2GateStatus,
    TokenLedgerIncomplete,
    TokenLedgerRow,
    TokenRowKind,
    build_token_report,
    parse_cache_multiplier,
)


def run_probe(
    *,
    root: Path = Path("."),
    output_path: Path = Path(".planning/spikes/d5.3-m2-token-ledger.json"),
    write_output: bool = True,
) -> dict:
    lock = tomllib.loads((root / "agy.lock").read_text())
    config = tomllib.loads((root / "config" / "defaults.toml").read_text())
    baseline_paths = lock["phase5_baselines"]
    opus_baseline_path = root / baseline_paths["opus_baseline_path"]
    opus_baseline = json.loads(opus_baseline_path.read_text())

    cache_mult = parse_cache_multiplier(lock["phase0"]["cache_mult"])
    target_ratio = float(config["phase5"]["m2_billable_token_ratio"])
    report = build_token_report(
        rows=_smoke_ledger_rows(),
        cache_mult=cache_mult,
        opus_baseline_billable_tokens=int(opus_baseline["billable_equivalent_tokens"]),
        target_ratio=target_ratio,
    )
    result = {
        "gate": "D5.3/m2-token-ledger",
        "passed": report.status == M2GateStatus.PASSED,
        "m2": {
            "status": report.status.value,
            "billable_equivalent_tokens": report.billable_equivalent_tokens,
            "threshold_tokens": report.threshold_tokens,
            "opus_baseline_billable_tokens": report.opus_baseline_billable_tokens,
            "target_ratio": report.target_ratio,
            "cache_mult": report.cache_mult,
            "row_counts_by_kind": report.row_counts_by_kind,
            "reported_only": report.reported_only,
            "rows": [asdict(row) for row in report.rows],
        },
        "provenance": {
            "cache_mult_pin": lock["phase0"]["cache_mult"],
            "opus_baseline_path": str(opus_baseline_path),
            "opus_workflow_sha": opus_baseline["workflow_sha"],
        },
    }
    if write_output:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def _smoke_ledger_rows() -> tuple[TokenLedgerRow, ...]:
    return (
        TokenLedgerRow("worker-1", TokenRowKind.WORKER, input_uncached=100, output=50),
        TokenLedgerRow("judge-1", TokenRowKind.JUDGE, input_uncached=20, output=10),
        TokenLedgerRow("retry-1", TokenRowKind.RETRY, input_uncached=10, output=5),
        TokenLedgerRow(
            "optimizer-1",
            TokenRowKind.OPTIMIZER_REVISION,
            input_uncached=8,
            output=4,
        ),
        TokenLedgerRow("escalation-1", TokenRowKind.ESCALATION, input_uncached=7, output=3),
        TokenLedgerRow("cache-write-1", TokenRowKind.CACHE_WRITE, input_uncached=30),
        TokenLedgerRow(
            "opaque-calibration-1",
            TokenRowKind.OPAQUE_ADAPTER_CALIBRATION,
            cached_read=10,
        ),
        TokenLedgerRow("tool-io-1", TokenRowKind.TOOL_IO, input_uncached=6, output=2),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".planning/spikes/d5.3-m2-token-ledger.json"),
    )
    args = parser.parse_args()
    try:
        result = run_probe(root=args.root, output_path=args.output)
    except TokenLedgerIncomplete as exc:
        print(json.dumps({"gate": "D5.3/m2-token-ledger", "passed": False, "error": str(exc)}))
        return 1
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "status": result["m2"]["status"],
                "billable_equivalent_tokens": result["m2"]["billable_equivalent_tokens"],
                "threshold_tokens": result["m2"]["threshold_tokens"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
