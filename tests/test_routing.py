"""FR-19 Phase-2 complexity router activation."""

from __future__ import annotations

import json
from pathlib import Path

from agy_swarms.routing import ComplexityRoute, route_complexity


def test_narrow_sequential_low_value_defaults_to_single_agent():
    decision = route_complexity("Rename one helper and update direct callers in one module.")

    assert decision.route == ComplexityRoute.SINGLE
    assert decision.fanout == 1
    assert decision.reason == "narrow_or_sequential"


def test_breadth_coupled_work_routes_to_small_fanout():
    decision = route_complexity(
        "Review four independent planning documents and summarize contradictions."
    )

    assert decision.route == ComplexityRoute.FANOUT_2_4
    assert decision.fanout == 4
    assert decision.reason == "bounded_parallel_breadth"


def test_broad_independent_suite_routes_to_large_fanout():
    decision = route_complexity(
        "Run a 12-task benchmark suite with independent workers and aggregate metrics."
    )

    assert decision.route == ComplexityRoute.FANOUT_10_PLUS
    assert decision.fanout == 10
    assert decision.reason == "broad_independent_breadth"


def test_unclear_task_fails_closed_to_single_agent():
    decision = route_complexity("Improve the project.")

    assert decision.route == ComplexityRoute.SINGLE
    assert decision.fanout == 1
    assert "default_single" in decision.concerns


def test_pinned_router_cases_match_phase2_minimum_routes():
    cases = json.loads(Path("benchmarks/router_cases.json").read_text())

    actual = {case["id"]: route_complexity(case["task"]).route.value for case in cases}

    assert actual == {
        "single_refactor": "single",
        "breadth_parallel_docs": "fanout(2-4)",
        "large_benchmark_suite": "fanout(10+)",
    }
