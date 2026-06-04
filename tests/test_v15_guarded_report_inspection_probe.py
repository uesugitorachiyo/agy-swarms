from __future__ import annotations

import json
import subprocess
import sys


def test_v15_guarded_report_inspection_probe_passes():
    result = subprocess.run(
        [sys.executable, "scripts/v15_guarded_report_inspection_probe.py"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["inspect_resume_summary_match"] is True
    assert payload["guarded_report_has_summary"] is True
    assert payload["unguarded_report_omits_summary"] is True
    assert payload["commands_executed"] is False
