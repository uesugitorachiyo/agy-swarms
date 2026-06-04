"""AC-30 / FR-25 deterministic obligation extraction and non-self closure binding."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from agy_swarms.quality.obligations import (
    Obligation,
    ObligationMergeError,
    VerificationSignal,
    closure_status,
    extract_obligations,
    merge_llm_obligations,
)


FIXTURES = Path(__file__).parent / "fixtures" / "obligations"


def test_extract_obligations_matches_pinned_fixture_exactly():
    spec_text = (FIXTURES / "spec_fixture.md").read_text()
    expected = json.loads((FIXTURES / "expected_obligations.json").read_text())

    extracted = extract_obligations(spec_text)

    assert [asdict(obligation) for obligation in extracted] == expected


def test_llm_proposal_cannot_drop_merge_or_weaken_extracted_obligation():
    extracted = extract_obligations((FIXTURES / "spec_fixture.md").read_text())
    proposal = [
        extracted[0],
        Obligation(
            id="clause:0002",
            text="NFR-2 The conductor MAY keep context bounded.",
            source="llm_proposed",
            source_ref="llm:1",
        ),
        Obligation(
            id="clause:merged",
            text="FR-9 and AC-30 are both generally covered.",
            source="llm_proposed",
            source_ref="llm:2",
        ),
    ]

    with pytest.raises(ObligationMergeError, match="cannot drop or weaken"):
        merge_llm_obligations(extracted, proposal)


def test_self_graded_only_obligation_blocks_done():
    obligation = Obligation(
        id="clause:0001",
        text="FR-9 The system SHALL implement dict-dispatch tools.",
        source="rfc2119",
        source_ref="line:3",
    )
    self_assertion = VerificationSignal(
        obligation_id=obligation.id,
        kind="test",
        artifact_pointer="tests/test_agent_loop.py::test_dict_dispatch",
        producer_node_id="implementer",
        verifier_node_id="implementer",
        verdict="passed",
    )

    status = closure_status([obligation], [self_assertion])

    assert status.closable is False
    assert status.blockers == (
        "clause:0001: no non-self passing verification with artifact pointer",
    )


def test_non_self_artifact_signal_closes_obligation():
    obligation = Obligation(
        id="clause:0001",
        text="FR-9 The system SHALL implement dict-dispatch tools.",
        source="rfc2119",
        source_ref="line:3",
    )
    signal = VerificationSignal(
        obligation_id=obligation.id,
        kind="test",
        artifact_pointer="tests/test_agent_loop.py::test_dict_dispatch",
        producer_node_id="implementer",
        verifier_node_id="reviewer",
        verdict="passed",
    )

    status = closure_status([obligation], [signal])

    assert status.closable is True
    assert status.blockers == ()
