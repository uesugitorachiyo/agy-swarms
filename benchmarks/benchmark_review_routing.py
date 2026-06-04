#!/usr/bin/env python3
"""Benchmark suite comparing agy, codex, claude, and off review routing pathways."""

from __future__ import annotations

import time
from pathlib import Path

from agy_swarms.adapters.scripted import CannedResult, ScriptedAdapter
from agy_swarms.budget import Dims
from agy_swarms.conductor import Conductor
from agy_swarms.types import Epoch, NodeSpec, TaskGraph


def run_benchmark_for_config(reviewer_adapter: str, closer_adapter: str) -> dict:
    # 1. Define a Task Graph containing both a reviewer and closer
    nodes = [
        NodeSpec(id="worker_node", role="worker", objective="implement code changes"),
        NodeSpec(
            id="reviewer_node",
            role="reviewer",
            objective="review code changes",
            dependencies=["worker_node"],
        ),
        NodeSpec(
            id="closer_node",
            role="closer",
            objective="verify and close task",
            dependencies=["reviewer_node"],
        ),
    ]
    graph = TaskGraph(nodes=nodes)

    # 2. Define standard canned results to simulate worker outputs
    scripted_responses = {
        "worker_node": CannedResult(
            status="succeeded",
            artifact={"ok": True},
            token_usage={
                "input": 500,
                "thinking": 200,
                "output": 100,
                "cached": 0,
                "accounting": "exact",
            },
        ),
        "reviewer_node": CannedResult(
            status="succeeded",
            artifact={"ok": True},
            token_usage={
                "input": 300,
                "thinking": 100,
                "output": 50,
                "cached": 0,
                "accounting": "exact",
            },
        ),
        "closer_node": CannedResult(
            status="succeeded",
            artifact={"ok": True},
            token_usage={
                "input": 200,
                "thinking": 50,
                "output": 30,
                "cached": 0,
                "accounting": "exact",
            },
        ),
    }
    adapter = ScriptedAdapter(scripted_responses)

    # 3. Measure latency and execute conductor
    start_time = time.perf_counter()
    conductor = Conductor(
        graph,
        adapter,
        limit=Dims(tokens=5000, usd=2.0),
        epoch=Epoch(epoch_seq=1, epoch_id="bench-epoch"),
        reviewer=reviewer_adapter,
        closer=closer_adapter,
    )
    report = conductor.run()
    latency = time.perf_counter() - start_time

    # 4. Extract token counts
    total_input = 0
    total_output = 0
    total_thinking = 0

    for result in report.results.values():
        usage = result.token_usage or {}
        total_input += usage.get("input", 0)
        total_output += usage.get("output", 0)
        total_thinking += usage.get("thinking", 0)

    # Note: Codex/Claude/Off routing adapters intercept review role execution
    # and return exact static evidence envelopes, consuming 0 LLM tokens.
    # We verify the correct adapter resolved the review nodes.
    reviewer_route = report.results["reviewer_node"].artifact.get("route", {}).get("adapter", "agy")
    closer_route = report.results["closer_node"].artifact.get("route", {}).get("adapter", "agy")

    return {
        "reviewer_adapter": reviewer_adapter,
        "closer_adapter": closer_adapter,
        "reviewer_resolved": reviewer_route,
        "closer_resolved": closer_route,
        "status": report.status.value,
        "latency_ms": latency * 1000,
        "tokens": {
            "input": total_input,
            "output": total_output,
            "thinking": total_thinking,
            "total": total_input + total_output + total_thinking,
        },
    }


def main():
    print("Running review routing benchmark suite...")

    configs = [
        ("agy", "agy"),
        ("codex", "codex"),
        ("claude", "claude"),
        ("off", "off"),
        ("codex", "agy"),
    ]

    results = []
    for reviewer_cfg, closer_cfg in configs:
        res = run_benchmark_for_config(reviewer_cfg, closer_cfg)
        results.append(res)
        print(
            f"Config ({reviewer_cfg}/{closer_cfg}) -> "
            f"Reviewer Resolved: {res['reviewer_resolved']}, Closer Resolved: {res['closer_resolved']}, "
            f"Total Tokens: {res['tokens']['total']}, Latency: {res['latency_ms']:.2f}ms"
        )

    # Build report markdown
    report_lines = [
        "# Review Routing Benchmarks",
        "",
        "This benchmark compares token usage, execution latency, and routing correctness across the supported review adapters.",
        "",
        "| Reviewer Adapter | Closer Adapter | Reviewer Resolved | Closer Resolved | Total LLM Tokens | Latency | Status |",
        "|---|---|---|---|---|---|---|",
    ]

    for r in results:
        report_lines.append(
            f"| {r['reviewer_adapter']} | {r['closer_adapter']} | {r['reviewer_resolved']} | {r['closer_resolved']} | {r['tokens']['total']} | {r['latency_ms']:.2f}ms | {r['status']} |"
        )

    report_lines.extend(
        [
            "",
            "### Architectural Insights",
            "- **`agy` Routing (Gemini Flash)**: Standard OAuth/Gemini transport for full agentic validation, pulling from `ScriptedAdapter` or live Gemini API.",
            "- **`codex` Routing (Codex CLI)**: Intercepted in read-only mode by the conductor, emitting structured verification evidence containing route metadata with zero additional LLM token cost.",
            "- **`claude` Routing (Claude CLI)**: Intercepted in read-only mode, serving as a future/optional CLI integration path with zero token cost.",
            "- **`off` Routing**: Bypasses validation entirely, completing the nodes with zero tokens and clean metadata.",
        ]
    )

    report_path = Path("benchmarks") / "review_routing_performance.md"
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(f"Benchmark results written to {report_path}")


if __name__ == "__main__":
    main()
