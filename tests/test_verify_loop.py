"""D4.1 evaluator-optimizer bounded verify loop."""

import pytest

from agy_swarms.quality.verify import (
    Revision,
    VerifyLoopStatus,
    run_evaluator_optimizer_loop,
)


def test_verify_loop_stops_immediately_when_verification_passes():
    report = run_evaluator_optimizer_loop(
        (),
        (),
        max_revisions=3,
        budget_tokens=100,
        generator_node_id="generator-1",
        verifier_node_id="verifier-1",
    )

    assert report.status == VerifyLoopStatus.PASSED
    assert report.terminated is True
    assert report.revisions == 0
    assert report.unresolved_defect_ids == ()
    assert report.steps == ()


def test_verify_loop_stops_at_max_revisions_with_unresolved_defects():
    report = run_evaluator_optimizer_loop(
        ("test:one", "lint:two"),
        (Revision(id="rev-1", addressed_defect_ids=("test:one",), cost_tokens=7),),
        max_revisions=1,
        budget_tokens=100,
        generator_node_id="generator-1",
        verifier_node_id="verifier-1",
    )

    assert report.status == VerifyLoopStatus.MAX_REVISIONS
    assert report.terminated is True
    assert report.revisions == 1
    assert report.unresolved_defect_ids == ("lint:two",)
    assert report.steps[0].revision_id == "rev-1"
    assert report.steps[0].addressed_defect_ids == ("test:one",)
    assert report.steps[0].spent_tokens == 7


def test_verify_loop_stops_on_budget_exhaustion_before_revision():
    report = run_evaluator_optimizer_loop(
        ("test:one",),
        (Revision(id="rev-expensive", addressed_defect_ids=("test:one",), cost_tokens=50),),
        max_revisions=2,
        budget_tokens=49,
        generator_node_id="generator-1",
        verifier_node_id="verifier-1",
    )

    assert report.status == VerifyLoopStatus.BUDGET_EXHAUSTED
    assert report.terminated is True
    assert report.revisions == 0
    assert report.unresolved_defect_ids == ("test:one",)
    assert report.steps == ()
    assert report.blockers == ("budget exhausted before rev-expensive",)


def test_verify_loop_rejects_non_monotonic_revision():
    report = run_evaluator_optimizer_loop(
        ("test:one",),
        (Revision(id="rev-stale", addressed_defect_ids=("schema:other",), cost_tokens=1),),
        max_revisions=2,
        budget_tokens=100,
        generator_node_id="generator-1",
        verifier_node_id="verifier-1",
    )

    assert report.status == VerifyLoopStatus.NON_MONOTONIC
    assert report.terminated is True
    assert report.revisions == 0
    assert report.unresolved_defect_ids == ("test:one",)
    assert report.blockers == ("revision rev-stale did not reduce unresolved defects",)


def test_verify_loop_records_separate_generator_and_verifier_contexts():
    report = run_evaluator_optimizer_loop(
        ("test:one",),
        (Revision(id="rev-1", addressed_defect_ids=("test:one",), cost_tokens=3),),
        max_revisions=2,
        budget_tokens=100,
        generator_node_id="generator-node",
        verifier_node_id="verifier-node",
    )

    assert report.status == VerifyLoopStatus.PASSED
    assert report.generator_node_id == "generator-node"
    assert report.verifier_node_id == "verifier-node"


def test_verify_loop_rejects_same_generator_and_verifier_context():
    with pytest.raises(ValueError, match="generator and verifier contexts must be separate"):
        run_evaluator_optimizer_loop(
            ("test:one",),
            (Revision(id="rev-1", addressed_defect_ids=("test:one",), cost_tokens=3),),
            max_revisions=2,
            budget_tokens=100,
            generator_node_id="same-node",
            verifier_node_id="same-node",
        )
