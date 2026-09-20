"""Competing-hypothesis and adaptivity contracts (Amendment 2).

Freezes H-turnover vs H-concentration with distinct failure_class and
mechanism, pre-registered directions, and a verified discriminating
pair: on shared candidate T-uni-tcs the frozen E2-D machinery computes
D=1 (unmodified selector code — this test only reads from it).
Hypotheses are derived from the frozen benchmark behaviour, never
fabricated for discrimination.
"""

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


def _hypotheses():
    return (
        Hypothesis(
            hypothesis_id="H-turnover",
            failure_class="turnover",
            mechanism=(
                "rule-based accumulation across two names sustains "
                "elevated order flow in low-volatility regimes"
            ),
            confidence=0.5,
            evidence_refs=("E3-C:benchmark-spec",),
        ),
        Hypothesis(
            hypothesis_id="H-concentration",
            failure_class="concentration",
            mechanism=(
                "persistent accumulation concentrates cost basis in "
                "the traded names"
            ),
            confidence=0.5,
            evidence_refs=("E3-C:benchmark-spec",),
        ),
    )


def _tests():
    return (
        DiagnosticTest(
            test_id="T-null",
            description="null control",
            target_failure_classes=("turnover", "concentration"),
            intervention={"type": "null_intervention"},
            measures=("turnover",),
            expected_discrimination="control",
            estimated_cost=1.0,
        ),
        DiagnosticTest(
            test_id="T-uni-tcs",
            description="restrict universe to TCS",
            target_failure_classes=("turnover", "concentration"),
            intervention={
                "type": "universe_restriction",
                "nse_equity": ["TCS:EQ"],
            },
            measures=("turnover", "concentration_cost_basis_max"),
            expected_discrimination="shared discriminating candidate",
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
    for hypothesis in _hypotheses():
        state.register_hypothesis(hypothesis)
    for test in _tests():
        state.register_test(test)
    return state


def test_hypothesis_ids_unique_and_class_mechanism_distinct():
    first, second = _hypotheses()
    assert first.hypothesis_id != second.hypothesis_id
    assert first.failure_class != second.failure_class
    for hypothesis in (first, second):
        assert hypothesis.failure_class != hypothesis.mechanism
        assert hypothesis.status.value == "PROPOSED"


def test_shared_candidate_computes_nonzero_discrimination():
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
            derivation_version="1",
        )
    )
    state.record_prediction(
        HypothesisPrediction(
            prediction_id="P2",
            hypothesis_id="H-concentration",
            test_id="T-uni-tcs",
            predicted_observable="concentration_cost_basis_max",
            expected_direction=ExpectedDirection.INCREASE,
            rationale="fewer names, higher concentration",
            derivation_method="E3-C-spec",
            derivation_version="1",
        )
    )
    eligible, _ = eligible_candidates(state)
    assert [t.test_id for t in eligible] == ["T-uni-tcs"]
    stats = candidate_statistics(state, eligible[0])
    assert stats.discrimination_pairs == 1
    assert stats.open_coverage == 2
    assert stats.selection_key() == (-1, -2, 1.0, "T-uni-tcs")
