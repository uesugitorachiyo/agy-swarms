from __future__ import annotations

import json
import subprocess
import sys


def test_v14_guarded_run_provenance_probe_passes():
    result = subprocess.run(
        [sys.executable, "scripts/v14_guarded_run_provenance_probe.py"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["guarded_report_has_provenance"] is True
    assert payload["unguarded_report_omits_provenance"] is True
    assert payload["commands_executed"] is False
