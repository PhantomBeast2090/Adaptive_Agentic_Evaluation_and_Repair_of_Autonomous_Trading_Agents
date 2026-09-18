"""Eligibility filtering: registered/executed/predicted/budget gates."""

import pytest

from evaluation.diagnostics.selection import select_next_test
from evaluation.diagnostics.selection.candidates import eligible_candidates

from ..fixtures import (
    make_hypothesis,
    make_prediction,
    make_rival,
    make_state,
    make_test,
)
from .fixtures import add_prediction, make_rival_state


def test_empty_state_has_no_eligible_candidates():
    state = make_state()
    eligible, verdicts = eligible_candidates(state)
    assert eligible == ()
    assert verdicts == ()
    out = select_next_test(state)
    assert type(out).__name__ == "NoCandidateResult"


def test_executed_candidate_excluded_with_reason():
    from ..fixtures import make_result

    state = make_rival_state()
    state.record_result(make_result(test=make_test(), prediction_ids=("P-1",)))
    eligible, verdicts = eligible_candidates(state)
    assert [t.test_id for t in eligible] == []
    assert verdicts[0].eligible is False
    assert "executed" in verdicts[0].reason


def test_predictionless_test_excluded_with_reason():
    state = make_state()
    state.register_hypothesis(make_hypothesis())
    state.register_test(make_test())
    eligible, verdicts = eligible_candidates(state)
    assert eligible == ()
    assert "no committed prediction" in verdicts[0].reason


def test_prediction_for_closed_hypothesis_does_not_qualify():
    from ..fixtures import make_result, make_update

    state = make_rival_state()
    state.record_result(make_result(test=make_test(), prediction_ids=("P-1",)))
    # Move H-1 and H-2 out of the open set via public update mechanics.
    for hid, status in (("H-1", "SUPPORTED"), ("H-2", "REJECTED")):
        prior = state.hypothesis(hid)
        update = make_update(update_id=f"U-{hid}", prior=prior)
        state.record_update(
            _update_with_status(update, prior, status)
        )
    eligible, _ = eligible_candidates(state)
    assert eligible == ()


def _update_with_status(update, prior, status):
    from evaluation.contracts.hypotheses import HypothesisStatus
    from evaluation.diagnostics.contracts.hypothesis_updates import (
        HypothesisUpdate,
    )

    return HypothesisUpdate(
        update_id=update.update_id,
        hypothesis_id=update.hypothesis_id,
        prior=prior,
        prior_fingerprint=prior.fingerprint(),
        prediction_id=update.prediction_id,
        result_id=update.result_id,
        compatibility=update.compatibility,
        assessment=update.assessment,
        updated=prior.with_status(HypothesisStatus(status)),
        updated_confidence=prior.confidence,
        evidence_refs=update.evidence_refs,
        method=update.method,
        version=update.version,
    )


def test_malformed_candidate_inputs_rejected():
    with pytest.raises(TypeError):
        eligible_candidates(object())
    with pytest.raises(TypeError):
        eligible_candidates("T-1")


def test_stopped_state_yields_no_candidate():
    from evaluation.contracts.stopping import StoppingReason

    state = make_rival_state()
    state.set_stopping_reason(StoppingReason.BUDGET_EXHAUSTED)
    out = select_next_test(state)
    assert type(out).__name__ == "NoCandidateResult"
    assert out.suggested_stopping == StoppingReason.BUDGET_EXHAUSTED
    assert len(state.rationales) == 0
    assert len(state.proposals) == 0
