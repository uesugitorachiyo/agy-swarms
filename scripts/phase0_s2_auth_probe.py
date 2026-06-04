#!/usr/bin/env python3
"""Run a Phase-0 S2/G0.2 agy auth-liveness and concurrency bootstrap probe.

This is not the final 24h+ soak. It is a short, repeatable bootstrap harness
that exercises the same independent canary shape the long soak will use:

- concurrent `agy -p` calls under PTY capture
- unique nonce per worker to detect output attribution/crosstalk
- auth and rate-limit failure classification
- JSON evidence written under `.planning/spikes/`
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import secrets
import shutil
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


AUTH_PATTERNS = (
    "not logged into antigravity",
    "failed to get oauth token",
    "error getting token source",
    "oauth",
)
RATE_LIMIT_PATTERNS = (
    "429",
    "rate limit",
    "resource exhausted",
    "quota",
)


@dataclass
class ProbeAttempt:
    round_index: int
    worker_index: int
    nonce: str
    ok: bool
    latency_s: float
    parsed: dict[str, Any] | None = None
    raw_response: str | None = None
    error: str | None = None
    failure_class: str | None = None


def clean_output(text: str) -> str:
    return text.replace("\x04", "").replace("\x08", "").strip()


def classify_failure(text: str) -> str:
    lowered = text.lower()
    if any(pattern in lowered for pattern in AUTH_PATTERNS):
        return "auth"
    if any(pattern in lowered for pattern in RATE_LIMIT_PATTERNS):
        return "rate_limit"
    return "other"


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


def validate_payload(payload: Any, nonce: str) -> tuple[bool, str | None]:
    if not isinstance(payload, dict):
        return False, "schema"
    if payload.get("nonce") != nonce:
        return False, "crosstalk"
    if payload.get("runtime") != "agy_antigravity_cli":
        return False, "schema"
    if payload.get("used_oauth_route") is not True:
        return False, "auth"
    if payload.get("verdict") not in {"pass", "fail"}:
        return False, "schema"
    if not isinstance(payload.get("summary"), str):
        return False, "schema"
    return True, None


async def run_one(
    cli: str,
    round_index: int,
    worker_index: int,
    print_timeout: str,
    timeout_s: int,
    use_pty: bool,
) -> ProbeAttempt:
    nonce = f"s2-r{round_index}-w{worker_index}-{secrets.token_hex(6)}"
    prompt = (
        "Return one JSON object only, with no markdown. "
        "Use this exact schema: "
        '{"verdict":"pass|fail","runtime":"agy_antigravity_cli",'
        '"nonce":"<nonce>","used_oauth_route":true,"summary":"short sentence"}. '
        f"The nonce is {nonce}. Echo it exactly. "
        "This is an agy/Antigravity CLI OAuth concurrency canary for Phase-0 S2/G0.2."
    )
    command = build_command(cli, prompt, print_timeout, use_pty)
    started = time.perf_counter()
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=timeout_s
        )
        latency_s = time.perf_counter() - started
        stdout = clean_output(stdout_bytes.decode(errors="replace"))
        stderr = clean_output(stderr_bytes.decode(errors="replace"))
        if process.returncode != 0:
            detail = stderr or stdout or f"{cli} exited {process.returncode}"
            return ProbeAttempt(
                round_index=round_index,
                worker_index=worker_index,
                nonce=nonce,
                ok=False,
                latency_s=latency_s,
                raw_response=stdout,
                error=detail,
                failure_class=classify_failure(detail),
            )
        parsed = extract_json(stdout)
        ok, failure_class = validate_payload(parsed, nonce)
        return ProbeAttempt(
            round_index=round_index,
            worker_index=worker_index,
            nonce=nonce,
            ok=ok,
            latency_s=latency_s,
            parsed=parsed,
            raw_response=stdout,
            failure_class=failure_class,
        )
    except Exception as exc:  # noqa: BLE001 - evidence probe records exact failures.
        latency_s = time.perf_counter() - started
        detail = f"{type(exc).__name__}: {exc}"
        return ProbeAttempt(
            round_index=round_index,
            worker_index=worker_index,
            nonce=nonce,
            ok=False,
            latency_s=latency_s,
            error=detail,
            failure_class=classify_failure(detail),
        )


async def run_probe(
    cli: str,
    concurrency: int,
    rounds: int,
    interval_s: float,
    print_timeout: str,
    timeout_s: int,
    use_pty: bool,
) -> dict[str, Any]:
    cli_path = shutil.which(cli)
    if cli_path is None:
        raise SystemExit(f"{cli!r} is not installed or not on PATH; cannot run the S2 auth probe.")

    attempts: list[ProbeAttempt] = []
    started = time.perf_counter()
    for round_index in range(1, rounds + 1):
        attempts.extend(
            await asyncio.gather(
                *(
                    run_one(cli, round_index, worker_index, print_timeout, timeout_s, use_pty)
                    for worker_index in range(1, concurrency + 1)
                )
            )
        )
        if round_index != rounds and interval_s > 0:
            await asyncio.sleep(interval_s)

    elapsed_s = time.perf_counter() - started
    latencies = [attempt.latency_s for attempt in attempts]
    total = len(attempts)
    ok_count = sum(1 for attempt in attempts if attempt.ok)
    failures_by_class: dict[str, int] = {}
    for attempt in attempts:
        if attempt.ok:
            continue
        failure_class = attempt.failure_class or "other"
        failures_by_class[failure_class] = failures_by_class.get(failure_class, 0) + 1
    return {
        "gate": "S2/G0.2-bootstrap",
        "transport": "agy_oauth",
        "cli": cli,
        "cli_path": cli_path,
        "concurrency": concurrency,
        "rounds": rounds,
        "total_attempts": total,
        "ok_count": ok_count,
        "success_rate": ok_count / total if total else 0.0,
        "p95_latency_s": p95(latencies),
        "elapsed_s": elapsed_s,
        "passed_bootstrap": ok_count == total,
        "pty_capture": use_pty,
        "failures_by_class": failures_by_class,
        "attempts": [asdict(attempt) for attempt in attempts],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", default="agy")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--interval-s", type=float, default=0.0)
    parser.add_argument("--print-timeout", default="5m0s")
    parser.add_argument("--timeout-s", type=int, default=330)
    parser.add_argument(
        "--output", type=Path, default=Path(".planning/spikes/s2-g0.2-auth-bootstrap.json")
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-pty", action="store_true")
    args = parser.parse_args()

    use_pty = not args.no_pty
    if args.dry_run:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "transport": "agy_oauth",
                    "cli": args.cli,
                    "cli_path": shutil.which(args.cli),
                    "concurrency": args.concurrency,
                    "rounds": args.rounds,
                    "total_attempts": args.concurrency * args.rounds,
                    "pty_capture": use_pty,
                    "script_available": shutil.which("script") is not None,
                    "contract": "concurrent PTY stdout + nonce JSON canary",
                    "final_soak": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    result = asyncio.run(
        run_probe(
            args.cli,
            args.concurrency,
            args.rounds,
            args.interval_s,
            args.print_timeout,
            args.timeout_s,
            use_pty,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                k: result[k]
                for k in [
                    "gate",
                    "transport",
                    "cli",
                    "concurrency",
                    "rounds",
                    "total_attempts",
                    "ok_count",
                    "success_rate",
                    "p95_latency_s",
                    "passed_bootstrap",
                    "failures_by_class",
                ]
            },
            indent=2,
        )
    )
    return 0 if result["passed_bootstrap"] else 1


if __name__ == "__main__":
    sys.exit(main())
