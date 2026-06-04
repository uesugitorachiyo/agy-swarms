"""AC-4 obligation-ledger closure hardening."""

from agy_swarms.quality.obligations import (
    VerificationSignal,
    evaluate_obligation_closure,
)


SPEC_TEXT = """\
- FR-25 The system SHALL keep an obligation ledger.
- AC-4 The closure gate MUST reject omitted obligations.
"""


def test_omitted_extracted_obligation_blocks_closure():
    report = evaluate_obligation_closure(
        SPEC_TEXT,
        (
            VerificationSignal(
                obligation_id="clause:0001",
                kind="test",
                artifact_pointer="tests/test_obligations_ac4.py::test_ledger",
                producer_node_id="implementer",
                verifier_node_id="reviewer",
                verdict="passed",
            ),
        ),
    )

    assert report.status.closable is False
    assert (
        "clause:0002: no non-self passing verification with artifact pointer"
        in report.status.blockers
    )
    assert (
        "id:AC-4: no non-self passing verification with artifact pointer" in report.status.blockers
    )
    assert tuple(obligation.id for obligation in report.obligations) == (
        "clause:0001",
        "clause:0002",
        "id:AC-4",
        "id:FR-25",
    )


def test_falsely_verified_obligation_without_artifact_pointer_blocks_closure():
    report = evaluate_obligation_closure(
        "FR-25 The system SHALL keep an obligation ledger.",
        (
            VerificationSignal(
                obligation_id="clause:0001",
                kind="test",
                artifact_pointer="",
                producer_node_id="implementer",
                verifier_node_id="reviewer",
                verdict="passed",
            ),
            VerificationSignal(
                obligation_id="id:FR-25",
                kind="test",
                artifact_pointer="tests/test_obligations_ac4.py::test_ledger",
                producer_node_id="implementer",
                verifier_node_id="implementer",
                verdict="passed",
            ),
        ),
    )

    assert report.status.closable is False
    assert report.status.blockers == (
        "clause:0001: no non-self passing verification with artifact pointer",
        "id:FR-25: no non-self passing verification with artifact pointer",
    )


def test_valid_non_self_artifact_pointers_close_all_obligations():
    report = evaluate_obligation_closure(
        "FR-25 The system SHALL keep an obligation ledger.",
        (
            VerificationSignal(
                obligation_id="clause:0001",
                kind="test",
                artifact_pointer="tests/test_obligations_ac4.py::test_clause",
                producer_node_id="implementer",
                verifier_node_id="reviewer",
                verdict="passed",
            ),
            VerificationSignal(
                obligation_id="id:FR-25",
                kind="lint",
                artifact_pointer="ruff:agy_swarms/quality/obligations.py",
                producer_node_id="implementer",
                verifier_node_id="reviewer",
                verdict="passed",
            ),
        ),
    )

    assert report.status.closable is True
    assert report.synthesis_handoff.unresolved_concerns == ()
    assert report.synthesis_handoff.closure_status == "closed"


def test_unresolved_concern_appears_in_synthesis_handoff_payload():
    report = evaluate_obligation_closure(SPEC_TEXT, ())

    assert report.status.closable is False
    assert report.synthesis_handoff.closure_status == "blocked"
    assert report.synthesis_handoff.unresolved_concerns == report.status.blockers
    assert "clause:0001: no non-self passing verification with artifact pointer" in (
        report.synthesis_handoff.unresolved_concerns
    )
