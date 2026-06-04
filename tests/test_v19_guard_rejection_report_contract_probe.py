from __future__ import annotations

import json
import subprocess
import sys


def test_v19_guard_rejection_report_contract_probe_passes():
    result = subprocess.run(
        [sys.executable, "scripts/v19_guard_rejection_report_contract_probe.py"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["guard_rejection_report_schema_valid"] is True
    assert payload["status"] == "rejected"
    assert payload["reason_class"] == "graph_digest_mismatch"
    assert payload["graph_sha256_match"] is False
    assert payload["commands_executed"] is False
    assert payload["marker_command_ran"] is False
    assert payload["stderr_redacted"] is True
    assert payload["repair_hint_present"] is True
    assert payload["rejection_scenarios"] == {
        "command_review_incomplete": True,
        "graph_digest_mismatch": True,
        "malformed_review_bundle": True,
    }
