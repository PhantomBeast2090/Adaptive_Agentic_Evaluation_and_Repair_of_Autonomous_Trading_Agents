"""Shared builders for E2-A contract tests (no execution, no LLM)."""

from evaluation.contracts.agent import AgentIdentity as _AgentIdentity
from evaluation.contracts.oracle import TargetObservation as _TargetObservation


class HoldAgentStub:
    """Minimal valid target agent: accepts only TargetObservation."""

    identity = _AgentIdentity("hold-stub", "0.1")

    def reset(self):
        return None

    def act(self, observation):
        if not isinstance(observation, _TargetObservation):
            raise TypeError("stub accepts only TargetObservation")
        return []

from evaluation.baseline.metrics import MetricResult
from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.budget import EvaluationBudget
from evaluation.contracts.diagnostic_tests import DiagnosticTest
from evaluation.contracts.hypotheses import Hypothesis, HypothesisStatus
from evaluation.diagnostics.contracts.diagnostic_state import DiagnosticState
from evaluation.diagnostics.contracts.hypothesis_updates import HypothesisUpdate
from evaluation.diagnostics.contracts.predictions import HypothesisPrediction
from evaluation.diagnostics.contracts.proposals import (
    CandidateAssessment,
    DiagnosticProposal,
    SelectionRationale,
)
from evaluation.diagnostics.contracts.test_results import DiagnosticTestResult


def make_hypothesis(hypothesis_id="H-1", mechanism="Overreacts to noise bursts."):
    return Hypothesis(
        hypothesis_id=hypothesis_id,
        failure_class="excessive_turnover",
        mechanism=mechanism,
        evidence_refs=("E-1",),
        confidence=0.5,
    )


def make_rival():
    return make_hypothesis(
        hypothesis_id="H-2",
        mechanism="Sizes positions unstably under volatility.",
    )


def make_test(test_id="T-1", multiplier=5.0):
    return DiagnosticTest(
        test_id=test_id,
        description="Shift transaction costs for one replay.",
        target_failure_classes=("excessive_turnover",),
        intervention={
            "type": "transaction_cost_shift",
            "multiplier": multiplier,
        },
        measures=("turnover",),
        expected_discrimination="Cost-sensitive turnover collapses.",
        estimated_cost=2.0,
    )


def make_state(diagnostic_id="D-1"):
    return DiagnosticState(
        diagnostic_id=diagnostic_id,
        baseline_evaluation_id="B-1",
        baseline_fingerprint="baseline-fp-1",
        agent_identity=AgentIdentity("agent-1", "0.1"),
        environment_spec={"market_fingerprint": "mfp-1"},
        config={},
        budget=EvaluationBudget(None, 10, None, None, None),
    )


def make_prediction(
    prediction_id="P-1", hypothesis_id="H-1", test_id="T-1",
    direction="DECREASE",
):
    return HypothesisPrediction(
        prediction_id=prediction_id,
        hypothesis_id=hypothesis_id,
        test_id=test_id,
        predicted_observable="turnover",
        expected_direction=direction,
        expected_magnitude="falls by at least half",
        rationale="Higher costs suppress churn under H-1.",
        derivation_method="manual-fixture",
        derivation_version="v1",
    )


def make_measured(value=1.2):
    return MetricResult(
        name="turnover",
        value=value,
        unit="ratio",
        derivation="e1.turnover.v1",
    )


def make_result(
    result_id="R-1",
    test=None,
    prediction_ids=("P-1",),
    status="COMPLETED",
    error=None,
):
    test = test or make_test()
    return DiagnosticTestResult(
        result_id=result_id,
        test_id=test.test_id,
        execution_fingerprint="exec-fp-1",
        baseline_evaluation_id="B-1",
        baseline_fingerprint="baseline-fp-1",
        intervention_fingerprint=test.fingerprint(),
        record_fps=("diag-record-1",),
        measured=(make_measured(),),
        prediction_ids=prediction_ids,
        status=status,
        error=error,
        provenance_method="manual-fixture-exec",
        provenance_version="v1",
    )


def make_update(update_id="U-1", prior=None, compatibility="SUPPORTS"):
    prior = prior or make_hypothesis()
    return HypothesisUpdate(
        update_id=update_id,
        hypothesis_id=prior.hypothesis_id,
        prior=prior,
        prior_fingerprint=prior.fingerprint(),
        prediction_id="P-1",
        result_id="R-1",
        compatibility=compatibility,
        assessment="Turnover fell as H-1 predicted.",
        updated=Hypothesis(
            hypothesis_id=prior.hypothesis_id,
            failure_class="excessive_turnover",
            mechanism=prior.mechanism,
            evidence_refs=("E-1", "R-1"),
            confidence=0.7,
            status=HypothesisStatus.SUPPORTED,
        ),
        updated_confidence=0.7,
        evidence_refs=("R-1",),
        method="rule:direction-match",
        version="v1",
    )


def make_rationale(rationale_id="SR-1"):
    return SelectionRationale(
        rationale_id=rationale_id,
        candidates=(
            CandidateAssessment(
                test_id="T-1",
                expected_discrimination="Separates H-1 from H-2.",
                estimated_cost=2.0,
            ),
            CandidateAssessment(
                test_id="T-2",
                expected_discrimination="Weak separator.",
                estimated_cost=9.0,
            ),
        ),
        selected_test_id="T-1",
        selection_score=0.8,
        method="manual-fixture",
        version="v1",
    )


def make_proposal(proposal_id="DP-1"):
    return DiagnosticProposal(
        proposal_id=proposal_id,
        hypothesis_ids=("H-1", "H-2"),
        prediction_ids=("P-1",),
        selected_test_id="T-1",
        expected_discrimination="Separates H-1 from H-2.",
        rationale_id="SR-1",
        confidence=0.6,
        alternative_test_ids=("T-2",),
        method="manual-fixture",
        version="v1",
    )


def make_full_state():
    """DiagnosticState with hypotheses, tests, rival predictions, a result,
    one update, rationale, proposal, and uncertainty recorded."""
    state = make_state()
    first = make_hypothesis()
    state.register_hypothesis(first)
    state.register_hypothesis(make_rival())
    test = make_test()
    state.register_test(test)
    state.register_test(make_test(test_id="T-2"))
    state.record_prediction(make_prediction())
    state.record_prediction(
        make_prediction(
            prediction_id="P-2",
            hypothesis_id="H-2",
            direction="NO_CHANGE",
        )
    )
    state.record_result(make_result())
    state.record_update(make_update())
    state.record_rationale(make_rationale())
    state.record_proposal(make_proposal())
    from evaluation.diagnostics.contracts.diagnostic_state import (
        UncertaintySnapshot,
    )

    state.record_uncertainty(
        UncertaintySnapshot(
            assessment_id="UA-1",
            method="manual-fixture",
            version="v1",
            open_hypothesis_ids=("H-2",),
            summary="H-1 supported; H-2 still open.",
        )
    )
    return state
