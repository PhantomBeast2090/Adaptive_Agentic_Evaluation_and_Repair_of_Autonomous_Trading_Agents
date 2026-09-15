"""Points 8, 9, 12: update prior preservation, references, duplicates."""

import pytest

from evaluation.contracts.hypotheses import HypothesisStatus
from evaluation.diagnostics.contracts.hypothesis_updates import (
    Compatibility,
    HypothesisUpdate,
)

from .fixtures import (
    make_full_state,
    make_hypothesis,
    make_prediction,
    make_result,
    make_state,
    make_test,
    make_update,
)


def _seeded_state():
    state = make_state()
    state.register_hypothesis(make_hypothesis())
    state.register_test(make_test())
    state.record_prediction(make_prediction())
    state.record_result(make_result())
    return state


def test_update_preserves_prior_state():
    state = _seeded_state()
    prior = state.hypothesis("H-1")
    state.record_update(make_update())
    current = state.hypothesis("H-1")
    assert current.status is HypothesisStatus.SUPPORTED
    assert current.confidence == 0.7
    (logged,) = state.hypothesis_updates
    assert logged.prior == prior
    assert logged.prior_fingerprint == prior.fingerprint()
    assert logged.updated == current
    # The log retains history while the working set advances.
    assert len(state.hypothesis_updates) == 1


def test_update_references_prediction_and_result():
    state = _seeded_state()
    update = make_update()
    bad_prediction = HypothesisUpdate(
        update_id="U-9",
        hypothesis_id="H-1",
        prior=state.hypothesis("H-1"),
        prior_fingerprint=state.hypothesis("H-1").fingerprint(),
        prediction_id="P-unknown",
        result_id="R-1",
        compatibility="SUPPORTS",
        assessment="x",
        updated=state.hypothesis("H-1"),
        updated_confidence=0.5,
        method="m",
        version="v",
    )
    with pytest.raises(ValueError):
        state.record_update(bad_prediction)
    bad_result = HypothesisUpdate(
        update_id="U-9",
        hypothesis_id="H-1",
        prior=state.hypothesis("H-1"),
        prior_fingerprint=state.hypothesis("H-1").fingerprint(),
        prediction_id="P-1",
        result_id="R-unknown",
        compatibility="SUPPORTS",
        assessment="x",
        updated=state.hypothesis("H-1"),
        updated_confidence=0.5,
        method="m",
        version="v",
    )
    with pytest.raises(ValueError):
        state.record_update(bad_result)
    state.record_update(update)
    assert len(state.hypothesis_updates) == 1


def test_update_rejects_stale_prior_and_duplicates():
    state = _seeded_state()
    state.record_update(make_update())
    stale = make_update(update_id="U-2")
    with pytest.raises(ValueError):
        state.record_update(stale)
    with pytest.raises(ValueError):
        state.record_update(make_update())
    assert len(state.hypothesis_updates) == 1


def test_update_validation_and_bayesian_claim_ban():
    prior = make_hypothesis()
    with pytest.raises(ValueError):
        make_update(update_id="U-x", compatibility="PROVEN")
    assert Compatibility.from_str("CONTRADICTS") is Compatibility.CONTRADICTS
    with pytest.raises(ValueError):
        HypothesisUpdate(
            update_id="U-x",
            hypothesis_id="H-1",
            prior=prior,
            prior_fingerprint=prior.fingerprint(),
            prediction_id="P-1",
            result_id="R-1",
            compatibility="SUPPORTS",
            assessment="x",
            updated=prior,
            updated_confidence=0.5,
            method="bayesian posterior update",
            version="v1",
        )
    update = make_update()
    restored = HypothesisUpdate.from_dict(update.to_dict())
    assert restored == update
    assert restored.fingerprint() == update.fingerprint()
    full = make_full_state()
    assert len(full.hypothesis_updates) == 1
