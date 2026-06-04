#!/usr/bin/env python3
"""Run the Phase-0 S4/G0.4 agy/Antigravity CLI worker-contract probe.

The intended v0 route is the Antigravity `agy` CLI using cached Google OAuth.
This probe checks the contract the engine can actually rely on over that route:

- non-interactive `agy -p` execution
- PTY capture, matching the documented `agy -p` stdout workaround
- prompt-level JSON worker artifact that can be parsed and validated

The installed `agy` surface does not expose a per-call `--model` flag or native
SDK `response_schema` / `thinking_config` objects, so model selection and
Flash-high thinking must be proven from agy configuration/transcript evidence in
Phase 0 rather than assumed from a command-line flag.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class ProbeAttempt:
    index: int
    ok: bool
    latency_s: float
    parsed: dict[str, Any] | None = None
    raw_response: str | None = None
    error: str | None = None


def validate_payload(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and payload.get("verdict") in {"pass", "fail"}
        and payload.get("runtime") == "agy_antigravity_cli"
        and payload.get("target_model_family") == "gemini-3.5-flash"
        and payload.get("thinking_level_requested") == "high"
        and isinstance(payload.get("used_oauth_route"), bool)
        and isinstance(payload.get("summary"), str)
    )


def clean_output(text: str) -> str:
    return text.replace("\x04", "").replace("\x08", "").strip()


def extract_json(text: str) -> dict[str, Any]:
    stripped = clean_output(text)
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("response JSON is not an object")
    return value


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[94]


def build_command(cli: str, prompt: str, print_timeout: str, use_pty: bool) -> list[str]:
    agy_cmd = [cli, "-p", prompt, "--print-timeout", print_timeout]
    if use_pty and shutil.which("script"):
        return ["script", "-q", "/dev/null", *agy_cmd]
    return agy_cmd


def run_cli_once(
    cli: str, print_timeout: str, timeout_s: int, use_pty: bool
) -> tuple[dict[str, Any], str]:
    prompt = (
        "Return one JSON object only, with no markdown. "
        "Use this exact schema: "
        '{"verdict":"pass|fail","runtime":"agy_antigravity_cli",'
        '"target_model_family":"gemini-3.5-flash",'
        '"thinking_level_requested":"high","used_oauth_route":true,'
        '"summary":"short sentence"}. '
        "This is an agy/Antigravity CLI OAuth worker-contract probe for Phase-0 S4/G0.4."
    )
    completed = subprocess.run(
        build_command(cli, prompt, print_timeout, use_pty),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    if completed.returncode != 0:
        stderr = clean_output(completed.stderr)
        stdout = clean_output(completed.stdout)
        detail = stderr or stdout or f"{cli} exited {completed.returncode}"
        raise RuntimeError(f"{cli} exited {completed.returncode}: {detail}")

    response = clean_output(completed.stdout)
    return extract_json(response), response


def run_probe(
    cli: str, n: int, print_timeout: str, timeout_s: int, use_pty: bool
) -> dict[str, Any]:
    cli_path = shutil.which(cli)
    if cli_path is None:
        raise SystemExit(
            f"{cli!r} is not installed or not on PATH; cannot run the agy/OAuth S4 probe."
        )

    attempts: list[ProbeAttempt] = []
    for index in range(1, n + 1):
        started = time.perf_counter()
        try:
            parsed, raw_response = run_cli_once(cli, print_timeout, timeout_s, use_pty)
            latency = time.perf_counter() - started
            attempts.append(
                ProbeAttempt(
                    index=index,
                    ok=validate_payload(parsed),
                    latency_s=latency,
                    parsed=parsed,
                    raw_response=raw_response,
                )
            )
        except Exception as exc:  # noqa: BLE001 - evidence probe records exact failures.
            latency = time.perf_counter() - started
            attempts.append(
                ProbeAttempt(
                    index=index,
                    ok=False,
                    latency_s=latency,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )

    latencies = [a.latency_s for a in attempts]
    adherence = sum(1 for a in attempts if a.ok) / n if n else 0.0
    return {
        "gate": "S4/G0.4",
        "transport": "agy_oauth",
        "cli": cli,
        "cli_path": cli_path,
        "n": n,
        "adherence": adherence,
        "p95_latency_s": p95(latencies),
        "passed": adherence >= 0.95,
        "pty_capture": use_pty,
        "per_call_model_flag": False,
        "attempts": [asdict(a) for a in attempts],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", default="agy")
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--print-timeout", default="5m0s")
    parser.add_argument("--timeout-s", type=int, default=330)
    parser.add_argument(
        "--output", type=Path, default=Path(".planning/spikes/s4-g0.4-results.json")
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-pty", action="store_true")
    args = parser.parse_args()

    cli_path = shutil.which(args.cli)
    use_pty = not args.no_pty
    if args.dry_run:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "transport": "agy_oauth",
                    "cli": args.cli,
                    "cli_path": cli_path,
                    "n": args.n,
                    "requires": [
                        "agy/Antigravity CLI on PATH",
                        "cached agy OAuth credentials",
                    ],
                    "pty_capture": use_pty,
                    "script_available": shutil.which("script") is not None,
                    "per_call_model_flag": False,
                    "native_sdk_composition": False,
                    "contract": "PTY stdout + prompt-level JSON artifact",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    result = run_probe(args.cli, args.n, args.print_timeout, args.timeout_s, use_pty)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                k: result[k]
                for k in ["gate", "transport", "cli", "n", "adherence", "p95_latency_s", "passed"]
            },
            indent=2,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
