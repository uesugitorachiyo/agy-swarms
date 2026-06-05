from agy_swarms.review_escalation import ReviewVerdict, decide_review_escalation


def test_escalates_when_agy_passes_and_codex_blocks():
    decision = decide_review_escalation(
        ReviewVerdict(source="agy", role="reviewer", verdict="pass"),
        ReviewVerdict(
            source="codex",
            role="reviewer",
            verdict="block",
            blockers=({"reason": "bug", "detail": "real issue"},),
        ),
    )

    assert decision.escalate is True
    assert decision.reason == "pass_block_disagreement"
    assert decision.target_model == "gpt-5.5"
    assert decision.reasoning_effort == "high"


def test_escalates_when_reviewer_has_concerns_but_closer_passes():
    decision = decide_review_escalation(
        ReviewVerdict(
            source="codex",
            role="reviewer",
            verdict="concerns",
            concerns=("missing regression test",),
        ),
        ReviewVerdict(source="codex", role="closer", verdict="pass"),
    )

    assert decision.escalate is True
    assert decision.reason == "reviewer_concern_closer_pass"


def test_does_not_escalate_when_reviewers_agree_on_pass():
    decision = decide_review_escalation(
        ReviewVerdict(source="agy", role="reviewer", verdict="pass"),
        ReviewVerdict(source="codex", role="reviewer", verdict="pass"),
    )

    assert decision.escalate is False
    assert decision.reason == "review_verdicts_agree"
