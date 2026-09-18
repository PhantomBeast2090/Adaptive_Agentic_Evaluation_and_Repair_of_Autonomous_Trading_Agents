"""End-to-end interpret() tests (mandate points 9-10, 15-17, 31-36)."""

import pytest

from evaluation.contracts.hypotheses import HypothesisStatus
from evaluation.diagnostics.contracts.predictions import HypothesisPrediction
from evaluation.diagnostics.interpretation.interpreter import interpret

from .fixtures import make_hypothesis, make_test
from .interpretation_fixtures import (
    make_baseline,
    make_diagnostic_result,
    make_interpret_state,
)


def test_competing_predictions_evaluated_independently():
    from evaluation.contracts.agent import AgentIdentity
    from evaluation.contracts.budget import EvaluationBudget
    from evaluation.diagnostics.contracts.diagnostic_state import (
        DiagnosticState,
    )
    from evaluation.diagnostics.contracts.predictions import (
        HypothesisPrediction as HP,
    )

    baseline = make_baseline({"turnover": 1.0})
    rivals = [
        make_hypothesis(),
        make_hypothesis(
            hypothesis_id="H-2",
            mechanism="Sizes positions unstably under volatility.",
        ),
        make_hypothesis(
            hypothesis_id="H-3", mechanism="Ignores cost schedules entirely."
        ),
    ]
    state = DiagnosticState(
        diagnostic_id="D-1",
        baseline_evaluation_id=baseline.evaluation_id,
        baseline_fingerprint=baseline.fingerprint(),
        agent_identity=AgentIdentity("agent-1", "0.1"),
        environment_spec={"market_fingerprint": "mfp-fixture"},
        config={},
        budget=EvaluationBudget(None, 10, None, None, None),
    )
    state.register_test(make_test())
    stances = []
    for index, hypothesis in enumerate(rivals):
        direction = ["INCREASE", "NO_CHANGE", "DECREASE"][index]
        stances.append(
            HP(
                prediction_id=f"PX-{index + 1}",
                hypothesis_id=hypothesis.hypothesis_id,
                test_id="T-1",
                predicted_observable="turnover",
                expected_direction=direction,
                rationale="Rival stances on one test.",
                derivation_method="manual-fixture",
                derivation_version="v1",
            )
        )
    for hypothesis, prediction in zip(rivals, stances):
        state.register_hypothesis(hypothesis)
        state.record_prediction(prediction)
    result = make_diagnostic_result(
        baseline,
        {"turnover": 1.2},
        prediction_ids=tuple(p.prediction_id for p in stances),
    )
    state.record_result(result)
    record = interpret(
        diagnostic_state=state,
        result_id=result.result_id,
        prediction_ids=[p.prediction_id for p in stances],
        baseline=baseline,
    )
    assert len(record.update_ids) == 3
    by_hypothesis = {
        u.hypothesis_id: u for u in state.hypothesis_updates
    }
    # obs 1.2 vs control 1.0: INCREASE supports, NO_CHANGE contradicts,
    # DECREASE contradicts — each judged alone, none ranked.
    assert by_hypothesis["H-1"].compatibility.value == "SUPPORTS"
    assert by_hypothesis["H-2"].compatibility.value == "CONTRADICTS"
    assert by_hypothesis["H-3"].compatibility.value == "CONTRADICTS"
    assert state.hypothesis("H-1").status is HypothesisStatus.UNRESOLVED
    assert state.hypothesis("H-2").status is HypothesisStatus.WEAKENED
    blob = str(record.to_dict())
    for token in ("rank", "winner", "best", "posterior"):
        assert token not in blob.lower()


def test_exactly_one_update_per_prediction():
    baseline = make_baseline({"turnover": 1.0})
    state, predictions = make_interpret_state(baseline)
    result = make_diagnostic_result(baseline, {"turnover": 0.8})
    state.record_result(result)
    record = interpret(
        diagnostic_state=state,
        result_id=result.result_id,
        prediction_ids=["P-1"],
        baseline=baseline,
    )
    assert len(record.update_ids) == 1
    assert len(state.hypothesis_updates) == 1
    update = state.hypothesis_updates[0]
    assert update.prediction_id == "P-1"
    assert update.result_id == "R-1"
    assert update.compatibility.value == "SUPPORTS"
    assert state.hypothesis("H-1").confidence == 0.6


def test_stale_and_double_interpretation_rejected():
    baseline = make_baseline({"turnover": 1.0})
    state, _ = make_interpret_state(baseline)
    result = make_diagnostic_result(baseline, {"turnover": 0.8})
    state.record_result(result)
    interpret(
        diagnostic_state=state,
        result_id=result.result_id,
        prediction_ids=["P-1"],
        baseline=baseline,
    )
    with pytest.raises(ValueError):
        interpret(
            diagnostic_state=state,
            result_id=result.result_id,
            prediction_ids=["P-1"],
            baseline=baseline,
        )
    # A hand-built update against the superseded prior is stale.
    from evaluation.diagnostics.interpretation.updates import build_update
    from evaluation.diagnostics.interpretation.comparison import Comparison
    from evaluation.diagnostics.contracts.hypothesis_updates import (
        Compatibility,
    )

    stale = build_update(
        update_id="U-stale",
        hypothesis=make_hypothesis(),
        prediction=state.predictions[0],
        result=result,
        comparison=Comparison(
            compatibility=Compatibility.SUPPORTS, detail="stale"
        ),
        observed_repr="0.8",
        control_repr="1.0",
    )
    with pytest.raises(ValueError):
        state.record_update(stale)
    assert len(state.hypothesis_updates) == 1


def test_sequential_tests_accumulate_history():
    baseline = make_baseline({"turnover": 1.0})
    state, _ = make_interpret_state(baseline)
    first = make_diagnostic_result(
        baseline, {"turnover": 0.8}, result_id="R-1"
    )
    state.record_result(first)
    interpret(
        diagnostic_state=state,
        result_id="R-1",
        prediction_ids=["P-1"],
        baseline=baseline,
    )
    assert state.hypothesis("H-1").status is HypothesisStatus.UNRESOLVED
    second = make_diagnostic_result(
        baseline, {"turnover": 1.5}, result_id="R-2"
    )
    state.record_result(second)
    interpret(
        diagnostic_state=state,
        result_id="R-2",
        prediction_ids=["P-1"],
        baseline=baseline,
    )
    assert len(state.hypothesis_updates) == 2
    # H-1 predicted DECREASE; 1.5 vs 1.0 contradicts -> WEAKENED @0.5.
    assert state.hypothesis("H-1").status is HypothesisStatus.WEAKENED
    assert state.hypothesis("H-1").confidence == 0.5
    priors = [u.prior_fingerprint for u in state.hypothesis_updates]
    assert len(set(priors)) == 2


def test_gates_unregistered_noncompleted_mismatched():
    baseline = make_baseline({"turnover": 1.0})
    state, _ = make_interpret_state(baseline)
    with pytest.raises(ValueError):
        interpret(
            diagnostic_state=state,
            result_id="R-ghost",
            prediction_ids=["P-1"],
            baseline=baseline,
        )
    failed = make_diagnostic_result(
        baseline, {"turnover": 0.8}, result_id="R-F",
        status="FAILED", error="executor blew up",
    )
    state.record_result(failed)
    with pytest.raises(ValueError):
        interpret(
            diagnostic_state=state,
            result_id="R-F",
            prediction_ids=["P-1"],
            baseline=baseline,
        )
    result = make_diagnostic_result(baseline, {"turnover": 0.8})
    state.record_result(result)
    with pytest.raises(ValueError):
        interpret(
            diagnostic_state=state,
            result_id="R-1",
            prediction_ids=["P-ghost"],
            baseline=baseline,
        )
    foreign = make_baseline({"turnover": 2.0}, evaluation_id="B-2")
    with pytest.raises(ValueError):
        interpret(
            diagnostic_state=state,
            result_id="R-1",
            prediction_ids=["P-1"],
            baseline=foreign,
        )
    with pytest.raises(TypeError):
        interpret(
            diagnostic_state=state,
            result_id="R-1",
            prediction_ids=["P-1"],
            baseline={"evaluation_id": "B-1"},
        )


def test_uncertainty_snapshot_deterministic():
    baseline = make_baseline({"turnover": 1.0})
    rivals = [
        make_hypothesis(),
        make_hypothesis(
            hypothesis_id="H-2",
            mechanism="Sizes positions unstably under volatility.",
        ),
    ]
    state, _ = make_interpret_state(
        baseline, hypotheses=rivals, directions=["DECREASE", "NO_CHANGE"]
    )
    result = make_diagnostic_result(
        baseline, {"turnover": 1.2}, prediction_ids=("P-1", "P-2")
    )
    state.record_result(result)
    record = interpret(
        diagnostic_state=state,
        result_id="R-1",
        prediction_ids=["P-1", "P-2"],
        baseline=baseline,
    )
    snapshot = state.uncertainty
    assert snapshot.assessment_id == record.uncertainty_id
    assert snapshot.assessment_id == "D-1:ua:R-1"
    # H-1 DECREASE vs 1.2 contradicts -> WEAKENED (open);
    # H-2 NO_CHANGE vs 1.2 contradicts -> WEAKENED (open).
    assert snapshot.open_hypothesis_ids == ("H-1", "H-2")
    assert "H-1 WEAKENED@0.4000" in snapshot.summary
    assert snapshot.method == "directional-band"
    assert snapshot.version == "v1"
    assert record.interpretation_id == "D-1:interp:R-1"
    assert record.method == "directional-band"
