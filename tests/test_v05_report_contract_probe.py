from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_report_schema_declares_stable_local_runner_fields():
    schema = json.loads(
        (ROOT / "schemas" / "local-runner-report-v1.schema.json").read_text(encoding="utf-8")
    )

    assert schema["$id"] == "https://agy-swarms.local/schemas/local-runner-report-v1.schema.json"
    assert schema["type"] == "object"
    assert set(schema["required"]) >= {
        "status",
        "states",
        "blockers",
        "spent_tokens",
        "spent_usd",
        "concerns",
        "changed_files",
        "results",
    }
    assert schema["properties"]["status"]["enum"] == ["succeeded", "failed"]
    assert "review_bundle_guard" not in schema["required"]
    guard = schema["properties"]["review_bundle_guard"]
    assert guard["properties"]["kind"]["const"] == "review_bundle_run_guard"
    assert guard["properties"]["guarded_run"]["const"] is True
    assert guard["properties"]["commands_executed"]["const"] is False


def test_v05_report_contract_probe_passes():
    summary_keys = [
        "blocker_count",
        "changed_files_count",
        "concern_count",
        "failed_nodes",
        "skipped_nodes",
        "status_counts",
        "total_nodes",
    ]
    result = subprocess.run(
        [sys.executable, "scripts/v05_report_contract_probe.py"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["gate"] == "V05-AC1/V05-AC2/V05-AC3"
    assert payload["passed"] is True
    assert payload["schema"] == "schemas/local-runner-report-v1.schema.json"
    assert {case["fixture"] for case in payload["cases"]} == {
        "success-graph.json",
        "failure-graph.json",
        "dependency-skip-graph.json",
    }
    assert all(case["schema_valid"] is True for case in payload["cases"])
    for case in payload["cases"]:
        assert case["inspect_summary_keys"] == summary_keys
        assert case["resume_status"] == "resume_loaded"
        assert case["resume_summary_keys"] == summary_keys
        assert case["resume_summary_keys"] == case["inspect_summary_keys"]
        assert case["resume_did_not_execute_commands"] is True
