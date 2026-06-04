import json
import subprocess
import sys


def test_v20_guard_rejection_inspection_probe_passes():
    result = subprocess.run(
        [sys.executable, "scripts/v20_guard_rejection_inspection_probe.py"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["guard_rejection_report_written"] is True
    assert payload["marker_command_ran"] is False
    assert payload["inspect_kind"] == "guard_rejection_report"
    assert payload["inspect_summary"]["reason_class"] == "graph_digest_mismatch"
    assert payload["resume_status"] == "resume_loaded"
    assert payload["resume_summary"] == payload["inspect_summary"]
