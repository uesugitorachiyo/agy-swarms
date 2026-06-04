"""D4.2 judge-panel soft evidence."""

import pytest

from agy_swarms.quality.judges import (
    JudgeModel,
    JudgePanelConfig,
    JudgePanelError,
    JudgeTransport,
    record_judge_verdict,
    summarize_judge_evidence,
    validate_judge_panel,
)


def test_panel_config_with_only_default_model_is_rejected():
    config = JudgePanelConfig(
        default_worker_model_id="gemini-3.5-flash-high",
        default_worker_transport=JudgeTransport.AGY_OAUTH,
        judges=(
            JudgeModel(
                id="judge-default",
                model_id="gemini-3.5-flash-high",
                transport=JudgeTransport.AGY_OAUTH,
            ),
        ),
    )

    with pytest.raises(JudgePanelError, match="at least one judge on a different model"):
        validate_judge_panel(config)


def test_panel_config_with_explicit_different_model_boundary_is_accepted():
    config = JudgePanelConfig(
        default_worker_model_id="gemini-3.5-flash-high",
        default_worker_transport=JudgeTransport.AGY_OAUTH,
        judges=(
            JudgeModel(
                id="judge-pro",
                model_id="gemini-3.5-pro",
                transport=JudgeTransport.GEMINI_SDK_API,
            ),
        ),
    )

    assert validate_judge_panel(config) is config


def test_different_model_judge_on_default_agy_oauth_boundary_is_rejected():
    config = JudgePanelConfig(
        default_worker_model_id="gemini-3.5-flash-high",
        default_worker_transport=JudgeTransport.AGY_OAUTH,
        judges=(
            JudgeModel(
                id="judge-pro",
                model_id="gemini-3.5-pro",
                transport=JudgeTransport.AGY_OAUTH,
            ),
        ),
    )

    with pytest.raises(JudgePanelError, match="model-configurable transport"):
        validate_judge_panel(config)


def test_judge_verdict_records_temperature_zero_model_rubric_and_artifact_pointer():
    verdict = record_judge_verdict(
        JudgeModel(
            id="judge-pro",
            model_id="gemini-3.5-pro",
            transport=JudgeTransport.GEMINI_SDK_API,
        ),
        rubric_sha="sha256:rubric",
        artifact_pointer="artifacts/candidate.md",
        passed=False,
        defects=("missing edge-case handling",),
    )

    assert verdict.temperature == 0.0
    assert verdict.model_id == "gemini-3.5-pro"
    assert verdict.transport == JudgeTransport.GEMINI_SDK_API
    assert verdict.rubric_sha == "sha256:rubric"
    assert verdict.artifact_pointer == "artifacts/candidate.md"
    assert verdict.defects == ("missing edge-case handling",)


def test_nonzero_temperature_judge_verdict_is_rejected():
    with pytest.raises(JudgePanelError, match="temperature=0"):
        record_judge_verdict(
            JudgeModel(
                id="judge-pro",
                model_id="gemini-3.5-pro",
                transport=JudgeTransport.GEMINI_SDK_API,
            ),
            rubric_sha="sha256:rubric",
            artifact_pointer="artifacts/candidate.md",
            passed=True,
            temperature=0.1,
        )


def test_judge_only_defect_is_soft_evidence_not_deterministic_gate():
    verdict = record_judge_verdict(
        JudgeModel(
            id="judge-pro",
            model_id="gemini-3.5-pro",
            transport=JudgeTransport.GEMINI_SDK_API,
        ),
        rubric_sha="sha256:rubric",
        artifact_pointer="artifacts/candidate.md",
        passed=False,
        defects=("answer lacks citations",),
    )

    report = summarize_judge_evidence((verdict,), ground_truth_available=False)

    assert report.evidence_type == "soft"
    assert report.deterministic_gate is False
    assert report.judge_only_defects == ("answer lacks citations",)
    assert report.ground_truth_preferred is False


def test_ground_truth_available_marks_judge_evidence_as_secondary():
    verdict = record_judge_verdict(
        JudgeModel(
            id="judge-pro",
            model_id="gemini-3.5-pro",
            transport=JudgeTransport.GEMINI_SDK_API,
        ),
        rubric_sha="sha256:rubric",
        artifact_pointer="artifacts/candidate.md",
        passed=False,
        defects=("style preference",),
    )

    report = summarize_judge_evidence((verdict,), ground_truth_available=True)

    assert report.evidence_type == "secondary_soft"
    assert report.deterministic_gate is False
    assert report.ground_truth_preferred is True
