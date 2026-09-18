"""Shared builders for E2-C interpretation tests (no execution, no env).

Baselines are hand-built frozen artefacts with caller-chosen metric
values — never reruns, never market data. Diagnostic states reuse the
E2-A fixture builders with baseline references rewired to the built
baseline artefact.
"""

from evaluation.baseline.config import BaselineConfig
from evaluation.baseline.metrics import MetricResult
from evaluation.baseline.results import BaselineResult
from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.budget import EvaluationBudget
from evaluation.contracts.decision_record import DecisionRecord
from evaluation.contracts.evaluation_state import EvaluationState
from evaluation.diagnostics.contracts.predictions import HypothesisPrediction

from .fixtures import make_hypothesis, make_test


def make_metric(name, value, reason="no observations in fixture"):
    if value is None:
        return MetricResult(
            name=name,
            value=None,
            unit="ratio",
            undefined_reason=reason,
            derivation="e1.fixture.v1",
        )
    return MetricResult(
        name=name, value=value, unit="ratio", derivation="e1.fixture.v1"
    )


def make_baseline(metrics, evaluation_id="B-1"):
    """Build a frozen BaselineResult with the given {name: value|None}."""
    agent = AgentIdentity("agent-1", "0.1")
    budget = EvaluationBudget(None, 10, None, None, None)
    record = DecisionRecord(
        decision_timestamp="2024-01-02",
        state_fingerprint="fp-fixture-1",
        visible_assets=("NIFTY_50",),
        unavailable_assets=("INDIA_VIX",),
        environment_metadata={"market_fingerprint": "mfp-fixture"},
        portfolio_before={"cash": 100000.0, "total_equity": 100000.0},
        portfolio_after={"cash": 100000.0, "total_equity": 100000.0},
    )
    config = BaselineConfig(
        evaluation_id=evaluation_id,
        start_date="2024-01-02",
        end_date="2024-01-02",
        universe={"nse_equity": ("RELIANCE:EQ",)},
        budget=budget,
    )
    state = EvaluationState(
        evaluation_id=evaluation_id,
        agent_identity=agent,
        environment_spec={"market_fingerprint": "mfp-fixture"},
        config={},
        budget=budget,
    )
    return BaselineResult(
        evaluation_id=evaluation_id,
        agent_identity=agent,
        environment_spec={"market_fingerprint": "mfp-fixture"},
        config=config,
        decision_records=(record,),
        metrics=tuple(
            make_metric(name, value) for name, value in metrics.items()
        ),
        evidence=(),
        evaluation_state=state,
        stopping_reason=None,
        budget_usage={"episodes": 1},
    )


def make_diagnostic_result(
    baseline,
    measured,
    prediction_ids=("P-1",),
    test=None,
    result_id="R-1",
    status="COMPLETED",
    error=None,
):
    """Build a COMPLETED result wired to the given baseline artefact."""
    from evaluation.diagnostics.contracts.test_results import (
        DiagnosticTestResult,
    )

    test = test or make_test()
    return DiagnosticTestResult(
        result_id=result_id,
        test_id=test.test_id,
        execution_fingerprint="exec-fp-fixture",
        baseline_evaluation_id=baseline.evaluation_id,
        baseline_fingerprint=baseline.fingerprint(),
        intervention_fingerprint=test.fingerprint(),
        record_fps=("diag-record-1",),
        measured=tuple(
            make_metric(name, value) for name, value in measured.items()
        ),
        prediction_ids=prediction_ids,
        status=status,
        error=error,
        provenance_method="manual-fixture-exec",
        provenance_version="v1",
    )


def make_interpret_state(baseline, hypotheses=None, test=None, directions=None):
    """DiagnosticState with hypotheses/test/predictions registered.

    Returns (state, predictions) with one prediction per hypothesis,
    all on the given test. ``directions`` optionally overrides the
    predicted direction per hypothesis, in order.
    """
    from evaluation.diagnostics.contracts.diagnostic_state import (
        DiagnosticState,
    )

    state = DiagnosticState(
        diagnostic_id="D-1",
        baseline_evaluation_id=baseline.evaluation_id,
        baseline_fingerprint=baseline.fingerprint(),
        agent_identity=AgentIdentity("agent-1", "0.1"),
        environment_spec={"market_fingerprint": "mfp-fixture"},
        config={},
        budget=EvaluationBudget(None, 10, None, None, None),
    )
    test = test or make_test()
    state.register_test(test)
    predictions = []
    for index, hypothesis in enumerate(hypotheses or [make_hypothesis()]):
        state.register_hypothesis(hypothesis)
        prediction = HypothesisPrediction(
            prediction_id=f"P-{index + 1}",
            hypothesis_id=hypothesis.hypothesis_id,
            test_id=test.test_id,
            predicted_observable="turnover",
            expected_direction="DECREASE",
            rationale="Higher costs suppress churn.",
            derivation_method="manual-fixture",
            derivation_version="v1",
        )
        state.record_prediction(prediction)
        predictions.append(prediction)
    return state, predictions
