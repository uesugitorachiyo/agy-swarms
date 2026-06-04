"""D4.0 code-owned ground-truth verify gate."""

from dataclasses import asdict

from agy_swarms.gates import run_gate
from agy_swarms.quality.verify import (
    GroundTruthSignal,
    VerifyStatus,
    ground_truth_verify_gate,
    verify_output,
)


def test_passing_ground_truth_signal_returns_passed_result():
    result = verify_output(
        {"artifact": "ok"},
        {
            "signals": [
                {
                    "id": "unit-tests",
                    "kind": "test",
                    "artifact_pointer": "tests/test_widget.py::test_ok",
                    "passed": True,
                }
            ]
        },
    )

    assert result.status == VerifyStatus.PASSED
    assert result.defect_ids == ()
    assert result.signal_count == 1


def test_failing_ground_truth_signal_returns_stable_failed_defect():
    result = verify_output(
        {"artifact": "bad"},
        {
            "signals": [
                {
                    "id": "unit-tests",
                    "kind": "test",
                    "artifact_pointer": "tests/test_widget.py::test_planted",
                    "passed": False,
                    "message": "expected 2 got 1",
                }
            ]
        },
    )

    assert result.status == VerifyStatus.FAILED
    assert result.defect_ids == ("test:unit-tests",)
    assert result.defects == (
        "test:unit-tests: tests/test_widget.py::test_planted failed: expected 2 got 1",
    )


def test_verify_gate_runs_through_fr33_double_execution_without_divergence():
    contract = {
        "signals": [
            asdict(
                GroundTruthSignal(
                    id="lint",
                    kind="lint",
                    artifact_pointer="ruff:agy_swarms/example.py",
                    passed=False,
                    message="F401 unused import",
                )
            )
        ]
    }

    verdict = run_gate(
        ground_truth_verify_gate,
        {"artifact": "candidate"},
        contract,
        gate_id="ground-truth-verify",
    )

    assert verdict.passed is False
    assert verdict.defects == ("lint:lint: ruff:agy_swarms/example.py failed: F401 unused import",)


def test_verify_output_rejects_unknown_signal_kind_as_failed_ground_truth():
    result = verify_output(
        {},
        {
            "signals": [
                {
                    "id": "mystery",
                    "kind": "astrology",
                    "artifact_pointer": "nowhere",
                    "passed": True,
                }
            ]
        },
    )

    assert result.status == VerifyStatus.FAILED
    assert result.defect_ids == ("invalid-signal:mystery",)
