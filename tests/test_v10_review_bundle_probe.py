from __future__ import annotations

import json
import subprocess
import sys


def test_v10_review_bundle_probe_passes():
    result = subprocess.run(
        [sys.executable, "scripts/v10_review_bundle_probe.py"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["gate"] == "V10-AC4"
    assert payload["passed"] is True
    assert {case["fixture"] for case in payload["cases"]} == {
        "success-graph.json",
        "failure-graph.json",
        "dependency-skip-graph.json",
    }
    assert all(case["schema_valid"] is True for case in payload["cases"])
    assert all(case["commands_executed"] is False for case in payload["cases"])
    assert all(case["byte_stable"] is True for case in payload["cases"])
