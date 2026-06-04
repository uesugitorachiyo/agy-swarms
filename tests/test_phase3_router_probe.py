from pathlib import Path

from scripts.phase3_ac3_router_probe import run_probe


def test_ac3_router_probe_reproduces_pinned_fixture_routes():
    result = run_probe(
        router_cases_path=Path("benchmarks/router_cases.json"),
        lockfile_path=Path("agy.lock"),
        write_output=False,
    )

    assert result["gate"] == "AC-3/router-fixture"
    assert result["passed"] is True
    assert result["accuracy"] == 1.0
    assert result["matched"] == result["total"] == 3
    assert result["router_cases_sha_matches_lock"] is True
    assert result["router_cases_sha"] == result["locked_router_cases_sha"]
    assert {case["id"] for case in result["cases"]} == {
        "single_refactor",
        "breadth_parallel_docs",
        "large_benchmark_suite",
    }
    assert all(case["matched"] for case in result["cases"])
