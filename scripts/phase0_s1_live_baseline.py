#!/usr/bin/env python3
"""Run the Phase-0 S1/G0.1 live single-agent baseline probe.

This harness materializes the pinned reference fixture, runs a single `agy -p`
repair turn against it, then verifies the fixture independently. It records
wall-clock and patch evidence. It does not fabricate token accounting: if the
CLI/logs do not expose token fields, S1 remains pending on that item.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from agy_swarms.canonical import canonical, sha256_hex

from phase0_s1_baseline_probe import FIXTURE_FILES


TOKEN_PATTERNS = (
    re.compile(
        r'"(?:input|prompt|output|completion|total|cached|thinking)[_-]?tokens"\s*:\s*(\d+)'
    ),
    re.compile(
        r"\b(?:input|prompt|output|completion|total|cached|thinking)[_-]?tokens\b[^0-9]{0,20}(\d+)"
    ),
)
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def clean_output(text: str) -> str:
    return text.replace("\x04", "").replace("\x08", "").strip()


def redact_sensitive(text: str) -> str:
    return EMAIL_PATTERN.sub("<redacted-email>", text)


def write_fixture(workspace: Path) -> None:
    if workspace.exists():
        shutil.rmtree(workspace)
    for relative, body in FIXTURE_FILES.items():
        path = workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)


def file_bytes(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative_parts = path.relative_to(root).parts
        if (
            "__pycache__" in relative_parts
            or ".pytest_cache" in relative_parts
            or relative_parts[0] == ".planning"
            or path.suffix == ".pyc"
        ):
            continue
        files[str(path.relative_to(root))] = path.read_bytes()
    return files


def text_diff(before: dict[str, bytes], after: dict[str, bytes]) -> str:
    lines: list[str] = []
    for relative in sorted(set(before) | set(after)):
        old = before.get(relative, b"").decode(errors="replace").splitlines(keepends=True)
        new = after.get(relative, b"").decode(errors="replace").splitlines(keepends=True)
        if old == new:
            continue
        lines.extend(
            difflib.unified_diff(
                old,
                new,
                fromfile=f"a/{relative}",
                tofile=f"b/{relative}",
            )
        )
    return "".join(lines)


def run_tests(workspace: Path) -> dict[str, Any]:
    env = os.environ.copy()
    src = str((workspace / "src").resolve())
    env["PYTHONPATH"] = (
        src if not env.get("PYTHONPATH") else f"{src}{os.pathsep}{env['PYTHONPATH']}"
    )
    started = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    return {
        "command": f"{sys.executable} -m pytest -q",
        "returncode": completed.returncode,
        "elapsed_s": time.perf_counter() - started,
        "stdout": clean_output(completed.stdout),
        "stderr": clean_output(completed.stderr),
        "passed": completed.returncode == 0,
    }


def build_command(
    cli: str, workspace: Path, prompt: str, print_timeout: str, log_file: Path, use_pty: bool
) -> list[str]:
    agy_cmd = [
        cli,
        "--add-dir",
        str(workspace),
        "--log-file",
        str(log_file),
        "--dangerously-skip-permissions",
        "-p",
        prompt,
        "--print-timeout",
        print_timeout,
    ]
    if use_pty and shutil.which("script"):
        return ["script", "-q", "/dev/null", *agy_cmd]
    return agy_cmd


def build_prompt() -> str:
    return """You are running the pinned Phase-0 S1/G0.1 single-agent reference task.

Workspace constraints:
- Edit only files inside the provided workspace.
- Do not use network services.
- Implement the bug fix in src/merge_fixture/merge.py.
- Preserve deterministic sorted-key output.
- Raise MergeConflict when scalar values conflict.
- Run: python -m pytest -q

Return one JSON object at the end with this schema:
{"status":"pass|fail","changed_files":["..."],"test_command":"...","test_result":"...","summary":"...","token_usage":null}

If token usage is not directly visible to you, keep token_usage null.
"""


def parse_token_evidence(*texts: str) -> dict[str, Any]:
    matches: list[int] = []
    for text in texts:
        for pattern in TOKEN_PATTERNS:
            matches.extend(int(match.group(1)) for match in pattern.finditer(text))
    return {
        "available": bool(matches),
        "observed_values": matches,
        "note": "No reliable token fields were exposed by agy stdout/logs."
        if not matches
        else "Token-like fields found; inspect before treating as billable-equivalent.",
    }


def run_agy(
    cli: str, workspace: Path, log_file: Path, print_timeout: str, timeout_s: int, use_pty: bool
) -> dict[str, Any]:
    cli_path = shutil.which(cli)
    if cli_path is None:
        raise SystemExit(f"{cli!r} is not installed or not on PATH.")

    prompt = build_prompt()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    command = build_command(cli, workspace, prompt, print_timeout, log_file, use_pty)
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    elapsed_s = time.perf_counter() - started
    stdout = clean_output(completed.stdout)
    stderr = clean_output(completed.stderr)
    raw_log_text = log_file.read_text(errors="replace") if log_file.exists() else ""
    log_text = redact_sensitive(raw_log_text)
    if raw_log_text and log_text != raw_log_text:
        log_file.write_text(log_text)
    return {
        "cli": cli,
        "cli_path": cli_path,
        "command_shape": "agy --add-dir <workspace> --log-file <log> --dangerously-skip-permissions -p <prompt>",
        "returncode": completed.returncode,
        "elapsed_s": elapsed_s,
        "stdout": redact_sensitive(stdout),
        "stderr": redact_sensitive(stderr),
        "log_file": str(log_file),
        "log_bytes": len(log_text.encode("utf-8")),
        "token_accounting": parse_token_evidence(stdout, stderr, raw_log_text),
        "passed_transport": completed.returncode == 0,
    }


def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    workspace = args.workspace
    log_file = args.log_file
    write_fixture(workspace)
    before = file_bytes(workspace)
    pre_tests = run_tests(workspace)
    agy_result = run_agy(
        args.cli, workspace, log_file, args.print_timeout, args.timeout_s, not args.no_pty
    )
    post_tests = run_tests(workspace)
    after = file_bytes(workspace)
    changed_files = sorted(
        relative
        for relative in set(before) | set(after)
        if before.get(relative) != after.get(relative)
    )
    diff = text_diff(before, after)
    return {
        "gate": "S1/G0.1-live-single-agent-baseline",
        "transport": "agy_oauth",
        "final_s1_gate": False,
        "reference_task_path": str(args.reference_task),
        "reference_task_sha": sha256_hex(args.reference_task.read_bytes()),
        "fixture_sha": sha256_hex(canonical(FIXTURE_FILES)),
        "workspace": str(workspace),
        "pre_tests": pre_tests,
        "agy": agy_result,
        "post_tests": post_tests,
        "changed_files": changed_files,
        "diff": diff,
        "diff_sha": sha256_hex(diff.encode()),
        "passed_live_repair": agy_result["passed_transport"]
        and post_tests["passed"]
        and bool(changed_files),
        "remaining_for_final_s1": [
            "actual billable-equivalent token baseline from agy accounting",
            "ao2 serial-repair wall-clock comparand on the same reference task",
            "factory-v3 wall-clock comparand for M3 two-way speed gate",
            "owner ratification of X_target after real baseline harvest",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", default="agy")
    parser.add_argument("--reference-task", type=Path, default=Path("benchmarks/reference_task.md"))
    parser.add_argument(
        "--workspace", type=Path, default=Path(".planning/spikes/s1-g0.1-live-baseline-workspace")
    )
    parser.add_argument(
        "--log-file", type=Path, default=Path(".planning/spikes/s1-g0.1-live-baseline-agy.log")
    )
    parser.add_argument(
        "--output", type=Path, default=Path(".planning/spikes/s1-g0.1-live-baseline.json")
    )
    parser.add_argument("--print-timeout", default="5m0s")
    parser.add_argument("--timeout-s", type=int, default=330)
    parser.add_argument("--no-pty", action="store_true")
    args = parser.parse_args()
    args.reference_task = args.reference_task.resolve()
    args.workspace = args.workspace.resolve()
    args.log_file = args.log_file.resolve()
    args.output = args.output.resolve()

    result = run_probe(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed_live_repair": result["passed_live_repair"],
                "agy_elapsed_s": result["agy"]["elapsed_s"],
                "post_tests_passed": result["post_tests"]["passed"],
                "changed_files": result["changed_files"],
                "token_accounting_available": result["agy"]["token_accounting"]["available"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed_live_repair"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
