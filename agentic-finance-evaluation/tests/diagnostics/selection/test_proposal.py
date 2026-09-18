"""Proposal/rationale creation, references, confidence, round-trips."""

import pytest

from evaluation.diagnostics.contracts.proposals import (
    DiagnosticProposal,
    SelectionRationale,
)
from evaluation.diagnostics.selection import select_next_test

from ..fixtures import make_hypothesis
from .fixtures import make_rival_state, make_three_way_state


def test_proposal_creation_and_rationale_linkage():
    state = make_rival_state()
    out = select_next_test(state)
    assert isinstance(out, DiagnosticProposal)
    assert out.selected_test_id == "T-1"
    assert out.method == "adaptive-discrimination"
    assert out.version == "v1"
    assert len(state.rationales) == 1
    assert len(state.proposals) == 1
    rationale = state.rationales[0]
    assert rationale.rationale_id == out.rationale_id
    assert rationale.method == "adaptive-discrimination"
    assert rationale.version == "v1"
    assert rationale.selection_score is None


def test_all_candidates_represented_and_selected_present():
    state = make_three_way_state()
    out = select_next_test(state)
    rationale = state.rationales[0]
    assert {c.test_id for c in rationale.candidates} == {"T-A", "T-B"}
    assert rationale.candidate(out.selected_test_id).test_id == (
        out.selected_test_id
    )


def test_alternatives_exclude_selected():
    state = make_three_way_state()
    out = select_next_test(state)
    assert out.selected_test_id not in out.alternative_test_ids
    assert set(out.alternative_test_ids) == {"T-B"}
    assert "rival hypothesis pairs separated" in out.expected_discrimination


def test_proposal_references_are_valid():
    state = make_rival_state()
    out = select_next_test(state)
    # Recording inside select_next_test already satisfied every frozen
    # reference invariant; re-assert the resolved content explicitly.
    assert set(out.hypothesis_ids) == {"H-1", "H-2"}
    assert set(out.prediction_ids) == {"P-1", "P-2"}
    assert out.hypothesis_ids == tuple(sorted(out.hypothesis_ids))
    assert out.prediction_ids == tuple(sorted(out.prediction_ids))


def test_structural_confidence_full_and_partial():
    full = select_next_test(make_rival_state())
    assert full.confidence == 1.0
    # Partial coverage: T-X carries predictions for H-1/H-2 only while H-3
    # stays open without one → C=2 of 3 open ⇒ confidence 2/3.
    from ..fixtures import make_state, make_test
    from .fixtures import add_prediction

    state = make_state()
    state.register_hypothesis(make_hypothesis())
    from ..fixtures import make_rival

    state.register_hypothesis(make_rival())
    state.register_hypothesis(
        make_hypothesis(
            hypothesis_id="H-3", mechanism="Stale information reuse."
        )
    )
    state.register_test(make_test(test_id="T-X"))
    add_prediction(state, "P-X1", "H-1", "T-X", "DECREASE")
    add_prediction(state, "P-X2", "H-2", "T-X", "INCREASE")
    out = select_next_test(state)
    assert out.selected_test_id == "T-X"
    assert out.confidence == pytest.approx(2.0 / 3.0)
    assert isinstance(out.confidence, float)
    assert 0.0 <= out.confidence <= 1.0


def test_confidence_is_not_hypothesis_confidence():
    state = make_rival_state()
    out = select_next_test(state)
    hypothesis_confidences = {
        h.hypothesis_id: h.confidence for h in state.hypotheses
    }
    assert hypothesis_confidences == {"H-1": 0.5, "H-2": 0.5}
    # Structural confidence derives from coverage/discrimination only.
    assert out.confidence == 1.0
    assert "probability" not in out.to_dict().__str__().lower()


def test_serialisation_round_trip_and_fingerprint():
    state = make_rival_state()
    out = select_next_test(state)
    restored = DiagnosticProposal.from_dict(out.to_dict())
    assert restored == out
    assert restored.fingerprint() == out.fingerprint()
    rationale = state.rationales[0]
    restored_r = SelectionRationale.from_dict(rationale.to_dict())
    assert restored_r == rationale
    assert restored_r.fingerprint() == rationale.fingerprint()
    with pytest.raises(ValueError):
        DiagnosticProposal.from_dict({**out.to_dict(), "nope": 1})
    with pytest.raises(ValueError):
        SelectionRationale.from_dict(
            {**rationale.to_dict(), "nope": 1}
        )


def test_malformed_references_rejected_at_record_time():
    from ..fixtures import make_proposal, make_rationale, make_state

    state = make_state()
    with pytest.raises(ValueError):
        state.record_proposal(make_proposal())
    with pytest.raises(ValueError):
        state.record_rationale(make_rationale())
