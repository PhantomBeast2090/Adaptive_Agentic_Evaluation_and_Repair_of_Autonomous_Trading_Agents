"""Single-hypothesis contracts (E3-C.2 revision).

Class-B carries exactly H-turnover. H-concentration was removed by the
E3-C narrow scientific audit (intervention-created, not a baseline
mechanism) and must not reappear here. With one open hypothesis the
frozen E2-D machinery computes D=0 for every candidate while coverage
reflects the single hypothesis — and the selector still returns a
valid deterministic candidate. E2-D is read from, never modified.
"""

import pytest

from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.budget import EvaluationBudget
from evaluation.contracts.diagnostic_tests import DiagnosticTest
from evaluation.contracts.hypotheses import Hypothesis
from evaluation.diagnostics.contracts.diagnostic_state import DiagnosticState
from evaluation.diagnostics.contracts.predictions import (
    ExpectedDirection,
    HypothesisPrediction,
)
from evaluation.diagnostics.selection.candidates import (
    candidate_statistics,
    eligible_candidates,
)
from evaluation.diagnostics.selection.selector import select_next_test


def _hypothesis():
    return Hypothesis(
        hypothesis_id="H-turnover",
        failure_class="turnover",
        mechanism=(
            "rule-based accumulation across two names sustains "
            "elevated order flow in low-volatility regimes"
        ),
        confidence=0.5,
        evidence_refs=("E3-C:benchmark-spec",),
    )


def _tests():
    return (
        DiagnosticTest(
            test_id="T-null",
            description="null control",
            target_failure_classes=("turnover",),
            intervention={"type": "null_intervention"},
            measures=("turnover",),
            expected_discrimination="control",
            estimated_cost=1.0,
        ),
        DiagnosticTest(
            test_id="T-uni-tcs",
            description="restrict universe to TCS",
            target_failure_classes=("turnover",),
            intervention={
                "type": "universe_restriction",
                "nse_equity": ["TCS:EQ"],
            },
            measures=("turnover",),
            expected_discrimination="order-flow restriction probe",
            estimated_cost=1.0,
        ),
    )


def _state():
    state = DiagnosticState(
        diagnostic_id="D-E3C",
        baseline_evaluation_id="B-E3C",
        baseline_fingerprint="fp",
        agent_identity=AgentIdentity("volatility-threshold-benchmark", "1.0"),
        environment_spec={"market_fingerprint": "mfp"},
        config={},
        budget=EvaluationBudget(None, 10, None, None, None),
    )
    state.register_hypothesis(_hypothesis())
    for test in _tests():
        state.register_test(test)
    return state


def test_only_h_turnover_registered_and_well_formed():
    hypothesis = _hypothesis()
    assert hypothesis.hypothesis_id == "H-turnover"
    assert hypothesis.failure_class == "turnover"
    assert hypothesis.failure_class != hypothesis.mechanism
    assert hypothesis.status.value == "PROPOSED"


def test_no_second_hypothesis_manufactured():
    state = _state()
    assert [h.hypothesis_id for h in state.hypotheses] == ["H-turnover"]


def test_single_hypothesis_yields_zero_discrimination():
    state = _state()
    state.record_prediction(
        HypothesisPrediction(
            prediction_id="P1",
            hypothesis_id="H-turnover",
            test_id="T-uni-tcs",
            predicted_observable="turnover",
            expected_direction=ExpectedDirection.DECREASE,
            rationale="fewer names, fewer orders",
            derivation_method="E3-C-spec",
            derivation_version="2",
        )
    )
    eligible, _ = eligible_candidates(state)
    assert [t.test_id for t in eligible] == ["T-uni-tcs"]
    stats = candidate_statistics(state, eligible[0])
    assert stats.discrimination_pairs == 0
    assert stats.open_coverage == 1
    assert stats.selection_key() == (0, -1, 1.0, "T-uni-tcs")


def test_selector_still_returns_deterministic_candidate():
    first = _state()
    first.record_prediction(
        HypothesisPrediction(
            prediction_id="P1",
            hypothesis_id="H-turnover",
            test_id="T-uni-tcs",
            predicted_observable="turnover",
            expected_direction=ExpectedDirection.DECREASE,
            rationale="fewer names, fewer orders",
            derivation_method="E3-C-spec",
            derivation_version="2",
        )
    )
    second = _state()
    second.record_prediction(
        HypothesisPrediction(
            prediction_id="P1",
            hypothesis_id="H-turnover",
            test_id="T-uni-tcs",
            predicted_observable="turnover",
            expected_direction=ExpectedDirection.DECREASE,
            rationale="fewer names, fewer orders",
            derivation_method="E3-C-spec",
            derivation_version="2",
        )
    )
    first_outcome = select_next_test(first)
    second_outcome = select_next_test(second)
    assert first_outcome.selected_test_id == "T-uni-tcs"
    assert (
        first_outcome.to_dict() == second_outcome.to_dict()
    )
