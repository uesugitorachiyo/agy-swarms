#!/usr/bin/env python3
"""AC-7/AC-8/AC-9 deterministic local runner probe for v0.2."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agy-v02-local-runner-") as tmp:
        tmp_path = Path(tmp)
        graph = tmp_path / "graph.json"
        report = tmp_path / "report.json"
        graph.write_text(
            json.dumps(
                {
                    "nodes": [
                        {
                            "id": "a",
                            "role": "test",
                            "objective": "echo a",
                            "command": [sys.executable, "-c", "print('a')"],
                        },
                        {
                            "id": "b",
                            "role": "verify",
                            "objective": "echo b",
                            "dependencies": ["a"],
                            "command": [sys.executable, "-c", "print('b')"],
                        },
                    ],
                    "edges": [["a", "b"]],
                }
            ),
            encoding="utf-8",
        )

        run_proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "agy_swarms.main",
                "run",
                "--graph",
                str(graph),
                "--allow-local-commands",
                "--report",
                str(report),
            ],
            capture_output=True,
            text=True,
        )
        if run_proc.returncode != 0:
            print(run_proc.stderr or run_proc.stdout, file=sys.stderr)
            return run_proc.returncode

        payload = json.loads(run_proc.stdout)
        inspect_proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "agy_swarms.main",
                "inspect",
                "--checkpoint",
                str(report),
            ],
            capture_output=True,
            text=True,
        )
        handoff_proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "agy_swarms.main",
                "handoff",
                "--report",
                str(report),
            ],
            capture_output=True,
            text=True,
        )

        passed = (
            payload["status"] == "succeeded"
            and payload["states"] == {"a": "succeeded", "b": "succeeded"}
            and payload["results"]["a"]["stdout"].strip() == "a"
            and payload["results"]["b"]["stdout"].strip() == "b"
            and report.exists()
            and inspect_proc.returncode == 0
            and json.loads(inspect_proc.stdout)["kind"] == "run_report"
            and handoff_proc.returncode == 0
            and "Do not implement changes" in handoff_proc.stdout
            and "do not push" in handoff_proc.stdout
            and _failure_resume_path_passes(tmp_path)
        )
        print(json.dumps({"gate": "AC-7/AC-8/AC-9", "passed": passed}, indent=2))
        return 0 if passed else 1


def _failure_resume_path_passes(tmp_path: Path) -> bool:
    counter = tmp_path / "counter.txt"
    graph = tmp_path / "failure-graph.json"
    report = tmp_path / "failure-report.json"
    graph.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "a",
                        "role": "test",
                        "objective": "increment once",
                        "command": [
                            sys.executable,
                            "-c",
                            (
                                "from pathlib import Path; "
                                f"p=Path({str(counter)!r}); "
                                "p.write_text(str(int(p.read_text() or '0') + 1)) "
                                "if p.exists() else p.write_text('1')"
                            ),
                        ],
                    },
                    {
                        "id": "b",
                        "role": "verify",
                        "objective": "fail",
                        "dependencies": ["a"],
                        "command": [sys.executable, "-c", "raise SystemExit(2)"],
                    },
                    {
                        "id": "c",
                        "role": "verify",
                        "objective": "skip after b",
                        "dependencies": ["b"],
                        "command": [sys.executable, "-c", "print('should-not-run')"],
                    },
                ],
                "edges": [["a", "b"], ["b", "c"]],
            }
        ),
        encoding="utf-8",
    )

    run_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "run",
            "--graph",
            str(graph),
            "--allow-local-commands",
            "--report",
            str(report),
        ],
        capture_output=True,
        text=True,
    )
    if run_proc.returncode != 1:
        return False
    payload = json.loads(run_proc.stdout)
    if payload["states"] != {"a": "succeeded", "b": "failed", "c": "skipped"}:
        return False

    inspect_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "inspect",
            "--checkpoint",
            str(report),
        ],
        capture_output=True,
        text=True,
    )
    resume_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "resume",
            "--checkpoint",
            str(report),
        ],
        capture_output=True,
        text=True,
    )

    return (
        report.exists()
        and counter.read_text(encoding="utf-8") == "1"
        and inspect_proc.returncode == 0
        and json.loads(inspect_proc.stdout)["states"]["c"] == "skipped"
        and resume_proc.returncode == 0
        and json.loads(resume_proc.stdout)["status"] == "resume_loaded"
        and counter.read_text(encoding="utf-8") == "1"
    )


if __name__ == "__main__":
    raise SystemExit(main())
