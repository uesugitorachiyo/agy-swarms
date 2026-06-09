import json
import subprocess
from pathlib import Path

from agy_swarms.review_benchmark import (
    ReviewBenchmarkCase,
    load_seeded_review_cases,
    run_review_benchmark,
)


def test_load_seeded_review_cases_contains_expected_labels():
    cases = load_seeded_review_cases(Path("benchmarks/review_seeded_cases.json"))

    assert len(cases) >= 5
    assert {case.id for case in cases} >= {
        "clean_reviewer_case",
        "missing_regression_test",
        "unsafe_local_command",
        "schema_invalid_output",
        "verified_closer_case",
    }
    assert all(case.expected_labels for case in cases)


def test_load_seeded_review_cases_default_is_independent_of_current_directory(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    cases = load_seeded_review_cases()

    assert {case.id for case in cases} >= {"clean_reviewer_case", "verified_closer_case"}


def test_run_review_benchmark_uses_codex_reasoning_profiles(tmp_path: Path):
    calls: list[list[str]] = []

    def fake_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        prompt = cmd[-1]
        if "unsafe_case" in prompt:
            output = {
                "summary": "Unsafe command execution blocks review.",
                "verdict": "block",
                "confidence": 0.91,
                "concerns": [],
                "blockers": [{"reason": "unsafe_command", "detail": "Permission is missing."}],
                "findings": [],
            }
        else:
            output = {
                "summary": "Review passed.",
                "verdict": "pass",
                "confidence": 0.84,
                "concerns": [],
                "blockers": [],
                "findings": [],
            }
        output_path.write_text(json.dumps(output), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="tokens used\n321\n", stderr="")

    cases = [
        ReviewBenchmarkCase(
            id="clean_case",
            role="reviewer",
            objective="clean_case",
            expected_verdict="pass",
        ),
        ReviewBenchmarkCase(
            id="unsafe_case",
            role="reviewer",
            objective="unsafe_case",
            expected_verdict="block",
        ),
    ]

    report = run_review_benchmark(
        cases,
        backends=("codex-low", "codex-high"),
        runner=fake_runner,
        cwd=tmp_path,
    )

    assert report["status"] == "completed"
    assert report["aggregate"]["codex-low"]["accuracy"] == 1.0
    assert report["aggregate"]["codex-high"]["accuracy"] == 1.0
    assert {cmd[cmd.index("-c") + 1] for cmd in calls} == {
        'model_reasoning_effort="low"',
        'model_reasoning_effort="high"',
    }
    assert report["results"][0]["token_output"] == 321
