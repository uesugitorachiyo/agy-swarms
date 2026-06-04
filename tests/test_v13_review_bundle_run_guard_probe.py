from __future__ import annotations

import json
import subprocess
import sys


def test_v13_review_bundle_run_guard_probe_passes():
    result = subprocess.run(
        [sys.executable, "scripts/v13_review_bundle_run_guard_probe.py"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["gate"] == "V13-AC4"
    assert payload["passed"] is True
    assert payload["matching_case"]["run_succeeded"] is True
    assert payload["mismatch_case"]["rejected_before_execution"] is True
    assert payload["mismatch_case"]["commands_executed"] is False
    assert payload["malformed_case"]["diagnostic_redacted"] is True
    assert payload["malformed_case"]["repairable"] is True
