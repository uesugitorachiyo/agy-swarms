import json
import subprocess
import sys


def test_v02_local_runner_probe_covers_ac8_failure_resume_path():
    proc = subprocess.run(
        [sys.executable, "scripts/v02_local_runner_probe.py"],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["gate"] == "AC-7/AC-8/AC-9"
    assert payload["passed"] is True
