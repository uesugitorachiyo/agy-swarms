from __future__ import annotations

import json
import subprocess
import sys


def test_v16_saved_report_summary_contract_probe_passes():
    result = subprocess.run(
        [sys.executable, "scripts/v16_saved_report_summary_contract_probe.py"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["guarded_inspect_schema_valid"] is True
    assert payload["guarded_resume_schema_valid"] is True
    assert payload["unguarded_inspect_schema_valid"] is True
    assert payload["unguarded_resume_schema_valid"] is True
    assert payload["inspect_resume_summary_match"] is True
    assert payload["commands_executed"] is False
