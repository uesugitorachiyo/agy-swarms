import json
import subprocess
import sys
from pathlib import Path


def test_v04_fixture_replay_probe_runs_tracked_fixtures():
    success_fixture = Path("tests/fixtures/local_runner/success-graph.json")
    failure_fixture = Path("tests/fixtures/local_runner/failure-graph.json")
    dependency_skip_fixture = Path("tests/fixtures/local_runner/dependency-skip-graph.json")
    assert success_fixture.exists()
    assert failure_fixture.exists()
    assert dependency_skip_fixture.exists()

    proc = subprocess.run(
        [sys.executable, "scripts/v04_fixture_replay_probe.py"],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr or proc.stdout
    payload = json.loads(proc.stdout)
    assert payload == {
        "gate": "V04-AC1/V04-AC2/V04-AC3",
        "passed": True,
        "fixtures": {
            "success": {
                "fixture": str(success_fixture),
                "passed": True,
                "resume_status": "resume_loaded",
                "resume_did_not_execute_commands": True,
                "status": "succeeded",
                "states": {
                    "prepare": "succeeded",
                    "verify": "succeeded",
                },
                "summary": {
                    "total_nodes": 2,
                    "status_counts": {"succeeded": 2},
                    "failed_nodes": [],
                    "skipped_nodes": [],
                    "blocker_count": 0,
                    "concern_count": 0,
                    "changed_files_count": 0,
                },
                "resume_summary": {
                    "total_nodes": 2,
                    "status_counts": {"succeeded": 2},
                    "failed_nodes": [],
                    "skipped_nodes": [],
                    "blocker_count": 0,
                    "concern_count": 0,
                    "changed_files_count": 0,
                },
            },
            "failure": {
                "fixture": str(failure_fixture),
                "passed": True,
                "resume_status": "resume_loaded",
                "resume_did_not_execute_commands": True,
                "status": "failed",
                "states": {
                    "prepare": "succeeded",
                    "unit": "failed",
                    "integration": "skipped",
                },
                "summary": {
                    "total_nodes": 3,
                    "status_counts": {
                        "failed": 1,
                        "skipped": 1,
                        "succeeded": 1,
                    },
                    "failed_nodes": ["unit"],
                    "skipped_nodes": ["integration"],
                    "blocker_count": 2,
                    "concern_count": 0,
                    "changed_files_count": 0,
                },
                "resume_summary": {
                    "total_nodes": 3,
                    "status_counts": {
                        "failed": 1,
                        "skipped": 1,
                        "succeeded": 1,
                    },
                    "failed_nodes": ["unit"],
                    "skipped_nodes": ["integration"],
                    "blocker_count": 2,
                    "concern_count": 0,
                    "changed_files_count": 0,
                },
            },
            "dependency_skip": {
                "fixture": str(dependency_skip_fixture),
                "passed": True,
                "resume_status": "resume_loaded",
                "resume_did_not_execute_commands": True,
                "status": "failed",
                "states": {
                    "root": "succeeded",
                    "lint": "failed",
                    "docs": "skipped",
                    "package": "skipped",
                },
                "summary": {
                    "total_nodes": 4,
                    "status_counts": {
                        "failed": 1,
                        "skipped": 2,
                        "succeeded": 1,
                    },
                    "failed_nodes": ["lint"],
                    "skipped_nodes": ["docs", "package"],
                    "blocker_count": 3,
                    "concern_count": 0,
                    "changed_files_count": 0,
                },
                "resume_summary": {
                    "total_nodes": 4,
                    "status_counts": {
                        "failed": 1,
                        "skipped": 2,
                        "succeeded": 1,
                    },
                    "failed_nodes": ["lint"],
                    "skipped_nodes": ["docs", "package"],
                    "blocker_count": 3,
                    "concern_count": 0,
                    "changed_files_count": 0,
                },
            },
        },
    }
