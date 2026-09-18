"""Builders for E2-D selector tests (state construction only, no execution)."""

from ..fixtures import (
    make_hypothesis,
    make_prediction,
    make_rival,
    make_state,
    make_test,
)


def add_prediction(state, pid, hid, tid, direction, observable="turnover"):
    from evaluation.diagnostics.contracts.predictions import (
        HypothesisPrediction,
    )

    prediction = HypothesisPrediction(
        prediction_id=pid,
        hypothesis_id=hid,
        test_id=tid,
        predicted_observable=observable,
        expected_direction=direction,
        rationale="Fixture stance.",
        derivation_method="test-fixture",
        derivation_version="v1",
    )
    state.record_prediction(prediction)
    return prediction


def make_costly_test(test_id, cost):
    from evaluation.contracts.diagnostic_tests import DiagnosticTest

    return DiagnosticTest(
        test_id=test_id,
        description="Cost-variant diagnostic test.",
        target_failure_classes=("excessive_turnover",),
        intervention={"type": "transaction_cost_shift", "multiplier": 5.0},
        measures=("turnover",),
        expected_discrimination="Separates cost-sensitive behaviour.",
        estimated_cost=cost,
    )


def make_rival_state():
    """H-1/H-2 open with opposing predictions on T-1 (D=1, C=2)."""
    state = make_state()
    state.register_hypothesis(make_hypothesis())
    state.register_hypothesis(make_rival())
    state.register_test(make_test())
    add_prediction(state, "P-1", "H-1", "T-1", "DECREASE")
    add_prediction(state, "P-2", "H-2", "T-1", "INCREASE")
    return state


def make_three_way_state():
    """H-1/H-2/H-3 open; T-A splits 2-vs-1 (D=2), T-B unanimous (D=0)."""
    state = make_state()
    state.register_hypothesis(make_hypothesis())
    state.register_hypothesis(make_rival())
    state.register_hypothesis(
        make_hypothesis(
            hypothesis_id="H-3", mechanism="Stale information reuse."
        )
    )
    state.register_test(make_test(test_id="T-A"))
    state.register_test(make_test(test_id="T-B"))
    add_prediction(state, "P-A1", "H-1", "T-A", "DECREASE")
    add_prediction(state, "P-A2", "H-2", "T-A", "INCREASE")
    add_prediction(state, "P-A3", "H-3", "T-A", "INCREASE")
    add_prediction(state, "P-B1", "H-1", "T-B", "INCREASE")
    add_prediction(state, "P-B2", "H-2", "T-B", "INCREASE")
    add_prediction(state, "P-B3", "H-3", "T-B", "INCREASE")
    return state
