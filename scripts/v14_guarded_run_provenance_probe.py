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


def _run_report(args: list[str], report_path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "run",
            "--graph",
            GRAPH_PATH,
            "--allow-local-commands",
            "--report",
            str(report_path),
            *args,
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return json.loads(report_path.read_text(encoding="utf-8"))


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bundle_path = root / "bundle.json"
        guarded_report_path = root / "guarded-report.json"
        unguarded_report_path = root / "unguarded-report.json"
        write_review_bundle(load_graph(GRAPH_PATH), graph_path=GRAPH_PATH, output_path=bundle_path)

        guarded = _run_report(
            ["--require-review-bundle", str(bundle_path)],
            guarded_report_path,
        )
        unguarded = _run_report([], unguarded_report_path)
        guard = guarded.get("review_bundle_guard", {})

        passed = (
            isinstance(guard, dict)
            and guard.get("kind") == "review_bundle_run_guard"
            and guard.get("guarded_run") is True
            and guard.get("graph_sha256_match") is True
            and guard.get("commands_executed") is False
            and guard.get("missing_command_reviews") == []
            and guard.get("mismatched_command_reviews") == []
            and "review_bundle_guard" not in unguarded
        )
        print(
            json.dumps(
                {
                    "passed": passed,
                    "guarded_report_has_provenance": "review_bundle_guard" in guarded,
                    "unguarded_report_omits_provenance": "review_bundle_guard" not in unguarded,
                    "commands_executed": guard.get("commands_executed")
                    if isinstance(guard, dict)
                    else None,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
