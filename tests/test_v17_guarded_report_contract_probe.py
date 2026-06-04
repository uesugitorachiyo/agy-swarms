from __future__ import annotations

import json
import subprocess
import sys


def test_v17_guarded_report_contract_probe_passes():
    result = subprocess.run(
        [sys.executable, "scripts/v17_guarded_report_contract_probe.py"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["guarded_report_schema_valid"] is True
    assert payload["guarded_report_has_guard"] is True
    assert payload["guarded_run"] is True
    assert payload["guard_commands_executed"] is False
    assert payload["unguarded_report_schema_valid"] is True
    assert payload["unguarded_report_omits_guard"] is True
    assert payload["inspect_resume_summary_match"] is True
    assert payload["resume_did_not_execute_commands"] is True
