"""Points 1-3, 7: prediction validity, immutability, pre-existence."""

import dataclasses

import pytest

from evaluation.diagnostics.contracts.predictions import (
    ExpectedDirection,
    HypothesisPrediction,
)

from .fixtures import make_prediction, make_state


def test_prediction_requires_registered_references():
    state = make_state()
    with pytest.raises(ValueError):
        state.record_prediction(make_prediction())
    from .fixtures import make_hypothesis, make_test

    state.register_hypothesis(make_hypothesis())
    with pytest.raises(ValueError):
        state.record_prediction(make_prediction())
    state.register_test(make_test())
    state.record_prediction(make_prediction())
    # Same (hypothesis, test) pair cannot be predicted twice.
    with pytest.raises(ValueError):
        state.record_prediction(make_prediction(prediction_id="P-9"))
    # Rival hypothesis may stake its own competing prediction on T-1.
    from .fixtures import make_rival

    state.register_hypothesis(make_rival())
    state.record_prediction(
        make_prediction(
            prediction_id="P-2", hypothesis_id="H-2", direction="NO_CHANGE"
        )
    )
    assert len(state.predictions) == 2


def test_prediction_is_immutable():
    prediction = make_prediction()
    with pytest.raises(dataclasses.FrozenInstanceError):
        prediction.confidence = 0.9  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        prediction.expected_direction = ExpectedDirection.INCREASE  # type: ignore[misc]


def test_prediction_validation():
    with pytest.raises(ValueError):
        make_prediction(prediction_id="  ")
    with pytest.raises(ValueError):
        HypothesisPrediction(
            prediction_id="P-x",
            hypothesis_id="H-1",
            test_id="T-1",
            predicted_observable="turnover",
            expected_direction="SOMETIMES",
            rationale="r",
            derivation_method="m",
            derivation_version="v",
        )
    with pytest.raises(ValueError):
        make_prediction(direction="DECREASE").__class__(
            prediction_id="P-x",
            hypothesis_id="H-1",
            test_id="T-1",
            predicted_observable="turnover",
            expected_direction="DECREASE",
            rationale="",
            derivation_method="m",
            derivation_version="v",
        )
    assert ExpectedDirection.from_str("INCREASE") is ExpectedDirection.INCREASE
    with pytest.raises(ValueError):
        ExpectedDirection.from_str("MAYBE")


def test_prediction_serialisation_round_trip():
    prediction = make_prediction()
    restored = HypothesisPrediction.from_dict(prediction.to_dict())
    assert restored == prediction
    assert restored.fingerprint() == prediction.fingerprint()
    assert restored.pair() == ("H-1", "T-1")
    with pytest.raises(ValueError):
        HypothesisPrediction.from_dict(
            {**prediction.to_dict(), "unknown_field": 1}
        )
