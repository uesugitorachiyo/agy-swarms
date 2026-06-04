#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from agy_swarms.graph_io import load_graph
from agy_swarms.review_bundle import write_review_bundle


GRAPH_PATH = "tests/fixtures/local_runner/success-graph.json"


def _run_cli(args: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "agy_swarms.main", *args],
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return json.loads(result.stdout)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bundle_path = root / "bundle.json"
        guarded_report_path = root / "guarded-report.json"
        unguarded_report_path = root / "unguarded-report.json"
        write_review_bundle(load_graph(GRAPH_PATH), graph_path=GRAPH_PATH, output_path=bundle_path)

        _run_cli(
            [
                "run",
                "--graph",
                GRAPH_PATH,
                "--allow-local-commands",
                "--require-review-bundle",
                str(bundle_path),
                "--report",
                str(guarded_report_path),
            ]
        )
        _run_cli(
            [
                "run",
                "--graph",
                GRAPH_PATH,
                "--allow-local-commands",
                "--report",
                str(unguarded_report_path),
            ]
        )
        inspected = _run_cli(["inspect", "--checkpoint", str(guarded_report_path)])
        resumed = _run_cli(["resume", "--checkpoint", str(guarded_report_path)])
        unguarded = _run_cli(["inspect", "--checkpoint", str(unguarded_report_path)])
        inspect_summary = inspected["summary"].get("guarded_report", {})
        resume_summary = resumed["summary"].get("guarded_report", {})
        passed = (
            inspect_summary == resume_summary
            and inspect_summary.get("has_review_bundle_guard") is True
            and inspect_summary.get("guarded_run") is True
            and inspect_summary.get("graph_sha256_match") is True
            and inspect_summary.get("review_complete") is True
            and inspect_summary.get("missing_command_review_count") == 0
            and inspect_summary.get("mismatched_command_review_count") == 0
            and inspect_summary.get("commands_executed") is False
            and resumed.get("status") == "resume_loaded"
            and "guarded_report" not in unguarded["summary"]
        )
        print(
            json.dumps(
                {
                    "passed": passed,
                    "inspect_resume_summary_match": inspect_summary == resume_summary,
                    "guarded_report_has_summary": bool(inspect_summary),
                    "unguarded_report_omits_summary": "guarded_report" not in unguarded["summary"],
                    "commands_executed": inspect_summary.get("commands_executed"),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
