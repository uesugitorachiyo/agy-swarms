#!/usr/bin/env python3
"""Verify read-only inspect/resume triage for guard rejection reports."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from agy_swarms.graph_io import load_graph
from agy_swarms.review_bundle import write_review_bundle


ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = ROOT / "tests" / "fixtures" / "local_runner" / "success-graph.json"


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agy_swarms.main", *args],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def _write_modified_graph(source: Path, destination: Path, marker: Path) -> None:
    payload = json.loads(source.read_text(encoding="utf-8"))
    for node in payload["nodes"]:
        if node["id"] == "verify":
            node["command"] = [
                sys.executable,
                "-c",
                f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
            ]
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_json(stdout: str) -> dict[str, Any]:
    payload = json.loads(stdout)
    if not isinstance(payload, dict):
        raise ValueError("CLI output was not a JSON object")
    return payload


def main() -> int:
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agy-v20-guard-rejection-inspection-") as tmp:
        workdir = Path(tmp)
        graph_path = workdir / "changed-graph.json"
        bundle_path = workdir / "review-bundle.json"
        report_path = workdir / "guard-rejection-report.json"
        marker_path = workdir / "marker.txt"
        _write_modified_graph(GRAPH_PATH, graph_path, marker_path)
        write_review_bundle(
            load_graph(str(GRAPH_PATH)),
            graph_path=str(GRAPH_PATH),
            output_path=bundle_path,
        )

        run = _run_cli(
            [
                "run",
                "--graph",
                str(graph_path),
                "--allow-local-commands",
                "--require-review-bundle",
                str(bundle_path),
                "--report",
                str(report_path),
            ]
        )
        if run.returncode != 1:
            errors.append(run.stderr or run.stdout or "guard rejection run did not fail")
        if not report_path.exists():
            errors.append("guard rejection report was not written")

        inspect = _run_cli(["inspect", "--checkpoint", str(report_path)])
        resume = _run_cli(["resume", "--checkpoint", str(report_path)])
        inspect_payload: dict[str, Any] = {}
        resume_payload: dict[str, Any] = {}
        if inspect.returncode != 0:
            errors.append(inspect.stderr or inspect.stdout or "inspect failed")
        else:
            inspect_payload = _load_json(inspect.stdout)
        if resume.returncode != 0:
            errors.append(resume.stderr or resume.stdout or "resume failed")
        else:
            resume_payload = _load_json(resume.stdout)

        inspect_summary = inspect_payload.get("summary", {})
        resume_summary = resume_payload.get("summary", {})
        if inspect_payload.get("kind") != "guard_rejection_report":
            errors.append(f"inspect kind was {inspect_payload.get('kind')!r}")
        if resume_payload.get("status") != "resume_loaded":
            errors.append(f"resume status was {resume_payload.get('status')!r}")
        if resume_payload.get("source_status") != "rejected":
            errors.append(f"resume source_status was {resume_payload.get('source_status')!r}")
        if inspect_summary != resume_summary:
            errors.append("inspect and resume summaries differed")

        payload = {
            "passed": not errors,
            "errors": errors,
            "guard_rejection_report_written": report_path.exists(),
            "marker_command_ran": marker_path.exists(),
            "inspect_kind": inspect_payload.get("kind"),
            "inspect_summary": inspect_summary,
            "resume_status": resume_payload.get("status"),
            "resume_source_status": resume_payload.get("source_status"),
            "resume_summary": resume_summary,
        }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
