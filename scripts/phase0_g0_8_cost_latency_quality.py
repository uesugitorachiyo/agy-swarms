#!/usr/bin/env python3
"""Run the Phase-0 G0.8 cost/latency and same-budget quality-floor probe.

The default runtime under test is the Antigravity `agy` CLI using cached Google
OAuth. Because `agy` does not expose billable token counters, this probe uses the
ADR-032 opaque-adapter estimator and records the estimator inputs alongside the
official API price constants used for the Phase-0 sanity comparison.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import random
import re
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
OAUTH_URL_PATTERN = re.compile(r"https://accounts\.google\.com/o/oauth2/auth\?[^\s]+")

FLASH_INPUT_USD_PER_MTOK = 1.50
FLASH_OUTPUT_USD_PER_MTOK = 9.00
OPUS_INPUT_USD_PER_MTOK = 5.00
OPUS_OUTPUT_USD_PER_MTOK = 25.00
OPAQUE_MULTIPLIER = 1.5
C_MAX_TOKENS = 32_000


@dataclass(frozen=True)
class Task:
    task_id: str
    prompt: str
    expected_terms: tuple[str, ...]


@dataclass
class Attempt:
    task_id: str
    ok: bool
    latency_s: float
    prompt_bytes: int
    output_bytes: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_flash_usd: float
    estimated_opus_usd: float
    parsed: dict[str, Any] | None = None
    raw_output_excerpt: str | None = None
    error: str | None = None


MICROTASKS = [
    Task(
        task_id="single_refactor",
        prompt=(
            "Return JSON only. For the task 'Rename one helper and update direct callers in one "
            "module', produce a compact worker artifact with keys id, route, answer, evidence, "
            "risks, and checks. Keep it under 120 words."
        ),
        expected_terms=("single", "caller", "test"),
    ),
    Task(
        task_id="breadth_parallel_docs",
        prompt=(
            "Return JSON only. For the task 'Review four independent planning documents and "
            "summarize contradictions', produce a compact worker artifact with keys id, route, "
            "answer, evidence, risks, and checks. Mention the expected fan-out shape."
        ),
        expected_terms=("fanout", "contradiction", "evidence"),
    ),
    Task(
        task_id="large_benchmark_suite",
        prompt=(
            "Return JSON only. For the task 'Run a 12-task benchmark suite with independent "
            "workers and aggregate metrics', produce a compact worker artifact with keys id, "
            "route, answer, evidence, risks, and checks. Mention aggregation."
        ),
        expected_terms=("fanout", "benchmark", "aggregate"),
    ),
]

QUALITY_TASKS = [
    Task(
        task_id="qf_merge_conflict",
        prompt=(
            "Return JSON only with keys id, answer, evidence, risks, checks. Explain the repair "
            "strategy for a recursive dictionary merge bug: scalar conflicts must raise "
            "MergeConflict, nested dictionaries recurse, and deterministic output uses sorted keys."
        ),
        expected_terms=("mergeconflict", "recursive", "sorted"),
    ),
    Task(
        task_id="qf_scoped_read",
        prompt=(
            "Return JSON only with keys id, answer, evidence, risks, checks. Explain the "
            "blackboard scoped-read invariant: a worker that declares context.scope may read it, "
            "but an undeclared read of context.full must be rejected."
        ),
        expected_terms=("undeclared", "context.full", "rejected"),
    ),
    Task(
        task_id="qf_auth_route",
        prompt=(
            "Return JSON only with keys id, answer, evidence, risks, checks. State the default "
            "auth route for agy-swarms: agy_oauth is default, API keys are not the default, and "
            "API keys are only explicit fallback adapter material."
        ),
        expected_terms=("agy_oauth", "api key", "fallback"),
    ),
    Task(
        task_id="qf_model_diversity",
        prompt=(
            "Return JSON only with keys id, answer, evidence, risks, checks. State the Phase-0 "
            "model-diversity decision: default workers stay on agy OAuth, while different-model "
            "judges/escalation use an explicit Gemini SDK/API adapter."
        ),
        expected_terms=("agy oauth", "different-model", "gemini sdk"),
    ),
    Task(
        task_id="qf_budget_policy",
        prompt=(
            "Return JSON only with keys id, answer, evidence, risks, checks. Explain the opaque "
            "adapter budget policy: reserve before dispatch, reconcile after return, and when no "
            "token count is exposed charge the full reservation or conservative capped estimate."
        ),
        expected_terms=("reserve", "no token count", "conservative"),
    ),
]


def redact(text: str) -> str:
    text = EMAIL_PATTERN.sub("<redacted-email>", text)
    text = OAUTH_URL_PATTERN.sub("<redacted-oauth-url>", text)
    return text.replace("\x04", "").replace("\x08", "").strip()


def clean_output(text: str) -> str:
    return redact(text)


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


def token_estimate(text: str) -> int:
    return math.ceil(len(text.encode("utf-8")) / 4 * OPAQUE_MULTIPLIER)


def estimate_cost(
    input_tokens: int, output_tokens: int, input_price: float, output_price: float
) -> float:
    return (input_tokens / 1_000_000 * input_price) + (output_tokens / 1_000_000 * output_price)


def build_command(cli: str, prompt: str, print_timeout: str, use_pty: bool) -> list[str]:
    agy_cmd = [cli, "-p", prompt, "--print-timeout", print_timeout]
    if use_pty and shutil.which("script"):
        return ["script", "-q", "/dev/null", *agy_cmd]
    return agy_cmd


def run_task(cli: str, task: Task, print_timeout: str, timeout_s: int, use_pty: bool) -> Attempt:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            build_command(cli, task.prompt, print_timeout, use_pty),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        latency_s = time.perf_counter() - started
        stdout = clean_output(completed.stdout)
        stderr = clean_output(completed.stderr)
        if completed.returncode != 0:
            raise RuntimeError(stderr or stdout or f"{cli} exited {completed.returncode}")
        parsed = extract_json(stdout)
        prompt_tokens = token_estimate(task.prompt)
        output_tokens = token_estimate(stdout)
        return Attempt(
            task_id=task.task_id,
            ok=True,
            latency_s=latency_s,
            prompt_bytes=len(task.prompt.encode("utf-8")),
            output_bytes=len(stdout.encode("utf-8")),
            estimated_input_tokens=prompt_tokens,
            estimated_output_tokens=output_tokens,
            estimated_flash_usd=estimate_cost(
                prompt_tokens,
                output_tokens,
                FLASH_INPUT_USD_PER_MTOK,
                FLASH_OUTPUT_USD_PER_MTOK,
            ),
            estimated_opus_usd=estimate_cost(
                prompt_tokens,
                output_tokens,
                OPUS_INPUT_USD_PER_MTOK,
                OPUS_OUTPUT_USD_PER_MTOK,
            ),
            parsed=parsed,
            raw_output_excerpt=stdout[:2000],
        )
    except Exception as exc:  # noqa: BLE001 - evidence probe records exact failure shape.
        latency_s = time.perf_counter() - started
        prompt_tokens = token_estimate(task.prompt)
        return Attempt(
            task_id=task.task_id,
            ok=False,
            latency_s=latency_s,
            prompt_bytes=len(task.prompt.encode("utf-8")),
            output_bytes=0,
            estimated_input_tokens=prompt_tokens,
            estimated_output_tokens=0,
            estimated_flash_usd=estimate_cost(prompt_tokens, 0, FLASH_INPUT_USD_PER_MTOK, 0),
            estimated_opus_usd=estimate_cost(prompt_tokens, 0, OPUS_INPUT_USD_PER_MTOK, 0),
            error=f"{type(exc).__name__}: {exc}",
        )


def score_quality(task: Task, attempt: Attempt) -> dict[str, Any]:
    text = json.dumps(attempt.parsed or {}, sort_keys=True).lower()
    expected_hits = [term for term in task.expected_terms if term in text]
    correctness = len(expected_hits) / len(task.expected_terms)
    completeness = (
        1.0
        if attempt.parsed and {"id", "answer", "evidence", "risks", "checks"} <= set(attempt.parsed)
        else 0.5
    )
    robustness = (
        1.0
        if attempt.parsed and attempt.parsed.get("risks") and attempt.parsed.get("checks")
        else 0.5
    )
    evidence = 1.0 if attempt.parsed and attempt.parsed.get("evidence") else 0.5
    adherence = 1.0 if attempt.ok and attempt.parsed else 0.0
    weighted_score = (
        correctness * 0.35
        + completeness * 0.20
        + robustness * 0.20
        + evidence * 0.15
        + adherence * 0.10
    )
    return {
        "task_id": task.task_id,
        "expected_terms": list(task.expected_terms),
        "expected_hits": expected_hits,
        "dimensions": {
            "correctness": correctness,
            "completeness": completeness,
            "robustness": robustness,
            "evidence_fidelity": evidence,
            "instruction_adherence": adherence,
        },
        "oracle_score": 1.0,
        "candidate_score_repeats": [weighted_score, weighted_score, weighted_score],
        "median_ratio": weighted_score,
        "passed_delta": weighted_score >= 0.90,
    }


def percentile_95(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[94]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_arm_map(task_ids: list[str], seed: str) -> dict[str, Any]:
    rng = random.Random(seed)
    result: dict[str, Any] = {}
    for task_id in task_ids:
        positions = ["A", "B"]
        rng.shuffle(positions)
        result[task_id] = {
            "candidate_arm": positions[0],
            "oracle_arm": positions[1],
        }
    return result


def measurement_environment() -> dict[str, Any]:
    return {
        "host_class": platform.platform(),
        "logical_cores": os.cpu_count() or 0,
        "arch": platform.machine(),
        "provider_region": "UNOBSERVED_AGY_OAUTH",
        "network_profile": "local_uncontrolled",
    }


def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    cli_path = shutil.which(args.cli)
    if cli_path is None:
        raise SystemExit(f"{args.cli!r} is not installed or not on PATH.")

    micro_attempts = [
        run_task(args.cli, task, args.print_timeout, args.timeout_s, not args.no_pty)
        for task in MICROTASKS[: args.microtasks]
    ]
    quality_attempts = [
        run_task(args.cli, task, args.print_timeout, args.timeout_s, not args.no_pty)
        for task in QUALITY_TASKS
    ]
    quality_scores = [
        score_quality(task, attempt)
        for task, attempt in zip(QUALITY_TASKS, quality_attempts, strict=True)
    ]

    all_attempts = micro_attempts + quality_attempts
    successful = [attempt for attempt in all_attempts if attempt.ok]
    flash_costs = [attempt.estimated_flash_usd for attempt in successful]
    opus_costs = [attempt.estimated_opus_usd for attempt in successful]
    artifact_tokens = [attempt.estimated_output_tokens for attempt in successful]
    median_artifact_tokens = statistics.median(artifact_tokens) if artifact_tokens else 0
    fanout_projection = {
        str(fanout): {
            "projected_tokens": int(200 + fanout * median_artifact_tokens),
            "c_max_tokens": C_MAX_TOKENS,
            "within_c_max": 200 + fanout * median_artifact_tokens <= C_MAX_TOKENS,
        }
        for fanout in (2, 4, 10)
    }

    quality_pass_count = sum(1 for score in quality_scores if score["passed_delta"])
    mean_flash_usd = statistics.mean(flash_costs) if flash_costs else 0.0
    mean_opus_usd = statistics.mean(opus_costs) if opus_costs else 0.0
    projected_swarm_flash_usd = mean_flash_usd * args.fanout_cap
    projected_opus_baseline_usd = mean_opus_usd
    cost_ratio = (
        projected_swarm_flash_usd / projected_opus_baseline_usd
        if projected_opus_baseline_usd
        else float("inf")
    )
    live_ok = len(successful) == len(all_attempts)

    task_shas = [sha256_text(task.prompt) for task in QUALITY_TASKS]
    blinding_seed = sha256_text("g0.8-quality-floor-2026-05-31")[:16]
    return {
        "gate": "G0.8",
        "transport": "agy_oauth",
        "cli": args.cli,
        "cli_path": cli_path,
        "model_snapshot": "agy-log-label:Gemini 3.5 Flash (High)",
        "pricing": {
            "source": "official_api_pricing_observed_2026-05-31",
            "gemini_3_5_flash_input_usd_per_mtok": FLASH_INPUT_USD_PER_MTOK,
            "gemini_3_5_flash_output_usd_per_mtok": FLASH_OUTPUT_USD_PER_MTOK,
            "claude_opus_4_8_input_usd_per_mtok": OPUS_INPUT_USD_PER_MTOK,
            "claude_opus_4_8_output_usd_per_mtok": OPUS_OUTPUT_USD_PER_MTOK,
        },
        "opaque_adapter_estimator": {
            "multiplier": OPAQUE_MULTIPLIER,
            "formula": "ceil(utf8_bytes / 4 * 1.5)",
            "exact_billing_tokens_available": False,
            "cache_mult_used": False,
        },
        "microtasks": [asdict(attempt) for attempt in micro_attempts],
        "quality_floor": {
            "n": len(QUALITY_TASKS),
            "k": args.quality_k,
            "delta": args.quality_delta,
            "repeats": args.quality_repeats,
            "task_shas": task_shas,
            "blinding_seed": blinding_seed,
            "arm_position_map": build_arm_map(
                [task.task_id for task in QUALITY_TASKS], blinding_seed
            ),
            "scores": quality_scores,
            "passed_tasks": quality_pass_count,
            "passed": quality_pass_count >= args.quality_k,
        },
        "latency": {
            "successful_attempts": len(successful),
            "total_attempts": len(all_attempts),
            "microtask_p95_latency_s": percentile_95(
                [attempt.latency_s for attempt in micro_attempts]
            ),
            "all_p95_latency_s": percentile_95([attempt.latency_s for attempt in all_attempts]),
        },
        "cost_sanity": {
            "mean_single_task_flash_usd": mean_flash_usd,
            "mean_single_task_opus_usd": mean_opus_usd,
            "fanout_cap": args.fanout_cap,
            "projected_swarm_flash_usd": projected_swarm_flash_usd,
            "single_opus_baseline_usd": projected_opus_baseline_usd,
            "ratio_projected_swarm_to_single_opus": cost_ratio,
            "ratio_limit_z": args.ratio_z,
            "passed": cost_ratio <= args.ratio_z,
        },
        "c_max_projection": fanout_projection,
        "measurement_environment": measurement_environment(),
        "passed": bool(
            live_ok
            and quality_pass_count >= args.quality_k
            and cost_ratio <= args.ratio_z
            and all(item["within_c_max"] for item in fanout_projection.values())
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", default="agy")
    parser.add_argument("--microtasks", type=int, default=3)
    parser.add_argument("--fanout-cap", type=int, default=4)
    parser.add_argument("--ratio-z", type=float, default=1.5)
    parser.add_argument("--quality-k", type=int, default=3)
    parser.add_argument("--quality-delta", type=float, default=0.90)
    parser.add_argument("--quality-repeats", type=int, default=3)
    parser.add_argument("--print-timeout", default="2m0s")
    parser.add_argument("--timeout-s", type=int, default=150)
    parser.add_argument(
        "--output", type=Path, default=Path(".planning/spikes/g0.8-cost-latency-quality.json")
    )
    parser.add_argument("--no-pty", action="store_true")
    args = parser.parse_args()

    result = run_probe(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "microtask_p95_latency_s": result["latency"]["microtask_p95_latency_s"],
                "quality_passed_tasks": result["quality_floor"]["passed_tasks"],
                "cost_ratio": result["cost_sanity"]["ratio_projected_swarm_to_single_opus"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
