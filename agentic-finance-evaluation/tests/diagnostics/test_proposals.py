"""Points 13-14: proposal schema validation and selection rationale."""

import pytest

from evaluation.diagnostics.contracts.proposals import (
    CandidateAssessment,
    DiagnosticProposal,
    SelectionRationale,
)

from .fixtures import (
    make_full_state,
    make_hypothesis,
    make_prediction,
    make_proposal,
    make_rationale,
    make_rival,
    make_state,
    make_test,
)


def _grounded_state():
    state = make_state()
    state.register_hypothesis(make_hypothesis())
    state.register_hypothesis(make_rival())
    state.register_test(make_test())
    state.register_test(make_test(test_id="T-2"))
    state.record_prediction(make_prediction())
    state.record_rationale(make_rationale())
    return state


def test_proposal_schema_validation():
    proposal = make_proposal()
    restored = DiagnosticProposal.from_dict(proposal.to_dict())
    assert restored == proposal
    assert restored.fingerprint() == proposal.fingerprint()
    with pytest.raises(ValueError):
        make_proposal(proposal_id="DP-x").__class__(
            proposal_id="DP-x",
            hypothesis_ids=(),
            prediction_ids=("P-1",),
            selected_test_id="T-1",
            expected_discrimination="x",
            rationale_id="SR-1",
            method="m",
            version="v",
        )
    with pytest.raises(ValueError):
        DiagnosticProposal(
            proposal_id="DP-x",
            hypothesis_ids=("H-1",),
            prediction_ids=("P-1",),
            selected_test_id="T-1",
            expected_discrimination="x",
            rationale_id="SR-1",
            alternative_test_ids=("T-1",),
            method="m",
            version="v",
        )


def test_proposal_references_must_resolve():
    state = _grounded_state()
    state.record_proposal(make_proposal())
    assert len(state.proposals) == 1
    with pytest.raises(ValueError):
        state.record_proposal(make_proposal())
    unknown_rationale = DiagnosticProposal(
        proposal_id="DP-3",
        hypothesis_ids=("H-1",),
        prediction_ids=("P-1",),
        selected_test_id="T-1",
        expected_discrimination="x",
        rationale_id="SR-ghost",
        method="m",
        version="v",
    )
    with pytest.raises(ValueError):
        state.record_proposal(unknown_rationale)
    unknown_test = DiagnosticProposal(
        proposal_id="DP-4",
        hypothesis_ids=("H-1",),
        prediction_ids=("P-1",),
        selected_test_id="T-ghost",
        expected_discrimination="x",
        rationale_id="SR-1",
        method="m",
        version="v",
    )
    with pytest.raises(ValueError):
        state.record_proposal(unknown_test)


def test_selection_rationale_captures_alternatives():
    rationale = make_rationale()
    assert [c.test_id for c in rationale.candidates] == ["T-1", "T-2"]
    assert rationale.candidate("T-2").estimated_cost == 9.0
    assert rationale.selection_score == 0.8
    with pytest.raises(KeyError):
        rationale.candidate("T-ghost")
    scoreless = SelectionRationale(
        rationale_id="SR-2",
        candidates=(
            CandidateAssessment(
                test_id="T-1",
                expected_discrimination="x",
                estimated_cost=1.0,
            ),
        ),
        selected_test_id="T-1",
        selection_score=None,
        method="manual-fixture",
        version="v1",
    )
    assert scoreless.selection_score is None
    with pytest.raises(ValueError):
        SelectionRationale(
            rationale_id="SR-3",
            candidates=(
                CandidateAssessment(
                    test_id="T-1",
                    expected_discrimination="x",
                    estimated_cost=1.0,
                ),
            ),
            selected_test_id="T-2",
            method="m",
            version="v",
        )
    restored = SelectionRationale.from_dict(rationale.to_dict())
    assert restored == rationale
    assert make_full_state().proposals[0].rationale_id == "SR-1"
