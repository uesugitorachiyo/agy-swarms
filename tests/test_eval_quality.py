"""D5.2 M1 quality scoring and confidence gate tests."""

import pytest

from agy_swarms.eval.quality import (
    M1GateStatus,
    QualityGateIncomplete,
    QualityJudgeConfig,
    QualityRunScore,
    build_quality_report,
)


def _make_judge_config(**overrides: object) -> QualityJudgeConfig:
    """Build a valid judge config with sensible defaults."""
    defaults: dict = {
        "judge_model_id": "gemini-3.5-flash",
        "temperature": 0,
        "rubric_hash": "19ef49e402fd076f13b53b4aaed11b9817953ea4cb42532b37686fdca4897eb3",
        "blinding_map": {"candidate": "A", "baseline": "B"},
        "panel_composition": ("gemini-3.5-flash",),
    }
    defaults.update(overrides)
    return QualityJudgeConfig(**defaults)


def _make_scores(
    ratios: tuple[float, ...] = (0.98, 0.99, 0.97, 1.0, 0.98),
) -> tuple[QualityRunScore, ...]:
    """Build run scores where candidate/baseline produces the given ratios."""
    return tuple(
        QualityRunScore(
            run_id=f"run-{i}",
            candidate_score=r,
            baseline_score=1.0,
        )
        for i, r in enumerate(ratios)
    )


# --- TDD focus 1: passing lower-bound fixture ---


def test_passing_lower_bound_fixture():
    # Ratios: (0.98, 0.99, 0.97, 1.0, 0.98), mean ≈ 0.984
    # With K=5, df=4, t_crit=2.132, stdev ≈ 0.0114, SE ≈ 0.0051
    # lower ≈ 0.984 - 2.132*0.0051 ≈ 0.973 > 0.95
    report = build_quality_report(
        scores=_make_scores((0.98, 0.99, 0.97, 1.0, 0.98)),
        judge_config=_make_judge_config(),
        ci_lower_threshold=0.95,
    )
    assert report.status == M1GateStatus.PASSED
    assert report.ci_lower_bound >= 0.95
    assert report.num_runs == 5
    assert report.threshold == 0.95


# --- TDD focus 2: point estimate above 0.95 but lower bound below 0.95 fails ---


def test_point_estimate_above_but_ci_lower_below_fails():
    # Ratios: (1.0, 0.90, 1.0, 0.90, 0.96), mean ≈ 0.952
    # stdev ≈ 0.0497, SE ≈ 0.0222, lower ≈ 0.952 - 2.132*0.0222 ≈ 0.905 < 0.95
    report = build_quality_report(
        scores=_make_scores((1.0, 0.90, 1.0, 0.90, 0.96)),
        judge_config=_make_judge_config(),
        ci_lower_threshold=0.95,
    )
    assert report.status == M1GateStatus.FAILED
    assert report.mean_ratio > 0.95  # Point estimate is above threshold
    assert report.ci_lower_bound < 0.95  # But CI lower bound is below


# --- TDD focus 3: missing rubric hash / temperature / blinding map blocks M1 ---


def test_missing_rubric_hash_blocks_m1():
    with pytest.raises(QualityGateIncomplete, match="rubric_hash"):
        build_quality_report(
            scores=_make_scores(),
            judge_config=_make_judge_config(rubric_hash=""),
            ci_lower_threshold=0.95,
        )


def test_nonzero_temperature_blocks_m1():
    with pytest.raises(QualityGateIncomplete, match="temperature"):
        build_quality_report(
            scores=_make_scores(),
            judge_config=_make_judge_config(temperature=0.7),
            ci_lower_threshold=0.95,
        )


def test_missing_blinding_map_blocks_m1():
    with pytest.raises(QualityGateIncomplete, match="blinding_map"):
        build_quality_report(
            scores=_make_scores(),
            judge_config=_make_judge_config(blinding_map={}),
            ci_lower_threshold=0.95,
        )


def test_missing_judge_model_id_blocks_m1():
    with pytest.raises(QualityGateIncomplete, match="judge_model_id"):
        build_quality_report(
            scores=_make_scores(),
            judge_config=_make_judge_config(judge_model_id=""),
            ci_lower_threshold=0.95,
        )


def test_missing_panel_composition_blocks_m1():
    with pytest.raises(QualityGateIncomplete, match="panel_composition"):
        build_quality_report(
            scores=_make_scores(),
            judge_config=_make_judge_config(panel_composition=()),
            ci_lower_threshold=0.95,
        )


# --- bare point estimate rejection ---


def test_single_run_rejected_as_bare_point_estimate():
    with pytest.raises(QualityGateIncomplete, match="bare point estimate"):
        build_quality_report(
            scores=_make_scores((0.99,)),
            judge_config=_make_judge_config(),
            ci_lower_threshold=0.95,
        )


def test_two_runs_are_accepted():
    report = build_quality_report(
        scores=_make_scores((0.99, 1.0)),
        judge_config=_make_judge_config(),
        ci_lower_threshold=0.95,
    )
    assert report.num_runs == 2
    assert report.status == M1GateStatus.PASSED


# --- ratio computation ---


def test_ratio_with_non_unit_baseline():
    scores = (
        QualityRunScore(run_id="r0", candidate_score=0.90, baseline_score=0.95),
        QualityRunScore(run_id="r1", candidate_score=0.92, baseline_score=0.95),
        QualityRunScore(run_id="r2", candidate_score=0.91, baseline_score=0.95),
        QualityRunScore(run_id="r3", candidate_score=0.93, baseline_score=0.95),
        QualityRunScore(run_id="r4", candidate_score=0.94, baseline_score=0.95),
    )
    report = build_quality_report(
        scores=scores,
        judge_config=_make_judge_config(),
        ci_lower_threshold=0.95,
    )
    # Mean ratio = mean(0.947, 0.968, 0.958, 0.979, 0.989) ≈ 0.968
    assert report.mean_ratio == pytest.approx(0.968, abs=0.01)
    assert report.status == M1GateStatus.PASSED


def test_zero_baseline_score_raises():
    scores = (
        QualityRunScore(run_id="r0", candidate_score=0.99, baseline_score=0.0),
        QualityRunScore(run_id="r1", candidate_score=0.98, baseline_score=1.0),
    )
    with pytest.raises(QualityGateIncomplete, match="baseline_score"):
        build_quality_report(
            scores=scores,
            judge_config=_make_judge_config(),
            ci_lower_threshold=0.95,
        )


# --- reported-only fields ---


def test_reported_only_includes_stdev_and_margin():
    report = build_quality_report(
        scores=_make_scores((0.98, 0.99, 0.97, 1.0, 0.98)),
        judge_config=_make_judge_config(),
        ci_lower_threshold=0.95,
    )
    assert "stdev" in report.reported_only
    assert "margin" in report.reported_only
    assert report.reported_only["stdev"] > 0
    assert report.reported_only["margin"] > 0


# --- high K run ---


def test_ten_runs_with_tight_scores_pass():
    report = build_quality_report(
        scores=_make_scores((0.98,) * 10),
        judge_config=_make_judge_config(),
        ci_lower_threshold=0.95,
    )
    assert report.status == M1GateStatus.PASSED
    assert report.ci_lower_bound == report.mean_ratio  # All identical → stdev=0
    assert report.num_runs == 10


# --- custom min_runs ---


def test_custom_min_runs_k5():
    # Only 3 runs but requiring K=5 should reject
    with pytest.raises(QualityGateIncomplete, match="3"):
        build_quality_report(
            scores=_make_scores((0.99, 0.98, 1.0)),
            judge_config=_make_judge_config(),
            ci_lower_threshold=0.95,
            min_runs=5,
        )
