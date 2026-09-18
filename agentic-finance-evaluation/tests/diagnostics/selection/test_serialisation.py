"""Deterministic identity and serialisation round-trips."""

import pytest

from evaluation.diagnostics.selection import NoCandidateResult, select_next_test
from evaluation.diagnostics.selection.results import NoCandidateResult as NC

from ..fixtures import make_state
from .fixtures import add_prediction, make_costly_test, make_rival_state


def test_no_candidate_round_trip_and_fingerprint():
    out = select_next_test(make_state())
    assert isinstance(out, NC)
    restored = NC.from_dict(out.to_dict())
    assert restored == out
    assert restored.fingerprint() == out.fingerprint()
    assert restored.suggested_stopping == out.suggested_stopping
    with pytest.raises(ValueError):
        NC.from_dict({**out.to_dict(), "unknown": 1})
    with pytest.raises(TypeError):
        NC.from_dict("not-a-mapping")


def test_proposal_identity_stable_on_unchanged_state():
    first_state = make_rival_state()
    first = select_next_test(first_state)
    second_state = make_rival_state()
    second = select_next_test(second_state)
    assert first.proposal_id == second.proposal_id
    assert first.fingerprint() == second.fingerprint()
    assert (
        first_state.rationales[0].rationale_id
        == second_state.rationales[0].rationale_id
    )
    assert (
        first_state.rationales[0].fingerprint()
        == second_state.rationales[0].fingerprint()
    )


def test_identity_changes_with_state_changes():
    from .fixtures import add_prediction

    base = select_next_test(make_rival_state()).proposal_id
    changed = make_rival_state()
    # A new candidate (new test + prediction) changes the selection
    # context, so identity must change.
    changed.register_test(make_costly_test("T-9", 3.0))
    add_prediction(changed, "P-9", "H-1", "T-9", "INCREASE")
    out = select_next_test(changed)
    assert out.proposal_id != base


def test_cost_change_alters_rationale_identity():
    from ..fixtures import make_hypothesis, make_rival
    from .fixtures import add_prediction, make_costly_test

    def _state_with_costs(cost):
        state = make_state(diagnostic_id="D-COST")
        state.register_hypothesis(make_hypothesis())
        state.register_hypothesis(make_rival())
        state.register_test(make_costly_test("T-1", cost))
        add_prediction(state, "P-1", "H-1", "T-1", "DECREASE")
        add_prediction(state, "P-2", "H-2", "T-1", "INCREASE")
        return state

    cheap = select_next_test(_state_with_costs(1.0))
    pricey_state = _state_with_costs(9.0)
    pricey = select_next_test(pricey_state)
    assert cheap.selected_test_id == pricey.selected_test_id == "T-1"
    assert cheap.proposal_id != pricey.proposal_id
    assert "estimated cost=9.0" in pricey.expected_discrimination
    assert "estimated cost=1.0" in cheap.expected_discrimination
