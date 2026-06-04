from __future__ import annotations

import json
import subprocess
import sys


def test_v12_review_bundle_diff_probe_passes():
    result = subprocess.run(
        [sys.executable, "scripts/v12_review_bundle_diff_probe.py"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["gate"] == "V12-AC4"
    assert payload["passed"] is True
    assert payload["diff_case"]["byte_stable"] is True
    assert payload["diff_case"]["commands_executed"] is False
    assert payload["diff_case"]["graph_changed"] is True
    assert payload["diff_case"]["command_changes"]["added"] == ["audit"]
    assert payload["diff_case"]["command_changes"]["changed"] == ["verify"]
    assert payload["malformed_case"]["diagnostic_redacted"] is True
