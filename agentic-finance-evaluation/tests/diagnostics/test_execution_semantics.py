"""E2-B execution semantics tests (mandate points 8-20, 34-35)."""

import pytest

from evaluation.baseline.config import BaselineConfig
from evaluation.baseline.runner import run_baseline
from evaluation.contracts.budget import EvaluationBudget
from evaluation.diagnostics.execution import execute

from .execution_fixtures import (
    BrokenOutputAgent,
    BuyOnceAgent,
    ExplodingAgent,
    HoldAgent,
    OutsideUniverseAgent,
    SMALL_ENV_CONFIG,
    baseline_spec,  # noqa: F401
    make_cost_test,
    make_episode_config,
    make_exec_state,
    make_null_test,
)


def _baseline_run():
    from evaluation.contracts.agent import AgentIdentity

    class BaselineHold:
        identity = AgentIdentity("hold-stub", "0.1")

        def reset(self):
            return None

        def act(self, observation):
            return []

    config = BaselineConfig(
        evaluation_id="B-EXE",
        start_date="2023-05-15",
        end_date="2023-05-26",
        universe={
            "nse_equity": ["RELIANCE:EQ", "TCS:EQ"],
            "mcx_gold": ["GOLDAUG2023"],
        },
        budget=EvaluationBudget(10, None, None, None, None),
    )
    return run_baseline(BaselineHold(), config)


def test_null_episode_reproduces_baseline_mechanics(baseline_spec):
    baseline = _baseline_run()
    state = make_exec_state(baseline_spec, "D-SEM-1")
    episode = execute(
        diagnostic_state=state,
        test_id="T-NULL",
        prediction_ids=("P-1",),
        target_agent=HoldAgent(),
        episode_config=make_episode_config(seed=7),
    )
    baseline_fps = [r.fingerprint() for r in baseline.decision_records]
    episode_fps = [r.fingerprint() for r in episode.decision_records]
    assert episode_fps == baseline_fps
    assert episode.result.record_fps == tuple(baseline_fps)


def test_cost_shift_separates_trajectory_from_baseline(baseline_spec):
    from evaluation.baseline.config import BaselineConfig as _BC

    buyer = BuyOnceAgent()
    buyer2 = BuyOnceAgent()
    config = _BC(
        evaluation_id="B-EXE-2",
        start_date="2023-05-15",
        end_date="2023-05-26",
        universe={
            "nse_equity": ["RELIANCE:EQ", "TCS:EQ"],
            "mcx_gold": ["GOLDAUG2023"],
        },
        budget=EvaluationBudget(10, None, None, None, None),
    )
    base_result = run_baseline(buyer, config)
    state2 = make_exec_state(baseline_spec, "D-SEM-2b", test=make_cost_test())
    episode = execute(
        diagnostic_state=state2,
        test_id="T-COST",
        prediction_ids=("P-1",),
        target_agent=buyer2,
        episode_config=make_episode_config(seed=7),
    )
    assert [r.fingerprint() for r in episode.decision_records] != [
        r.fingerprint() for r in base_result.decision_records
    ]
    assert episode.result.measured_by_name("turnover").value is not None


def test_baseline_artefact_untouched_and_referenced(baseline_spec):
    baseline = _baseline_run()
    snapshot = baseline.to_dict()
    state = _state_with_baseline_refs(baseline_spec, baseline, "D-SEM-3")
    episode = execute(
        diagnostic_state=state,
        test_id="T-NULL",
        prediction_ids=("P-1",),
        target_agent=HoldAgent(),
        episode_config=make_episode_config(seed=7),
    )
    assert baseline.to_dict() == snapshot
    assert episode.result.baseline_evaluation_id == "B-EXE"
    assert episode.result.baseline_fingerprint == baseline.fingerprint()


def _state_with_baseline_refs(baseline_spec, baseline, diagnostic_id):
    from evaluation.contracts.agent import AgentIdentity
    from evaluation.contracts.budget import EvaluationBudget as _EB
    from evaluation.contracts.hypotheses import Hypothesis
    from evaluation.diagnostics.contracts.diagnostic_state import (
        DiagnosticState,
    )
    from evaluation.diagnostics.contracts.predictions import (
        HypothesisPrediction as _HP,
    )

    state = DiagnosticState(
        diagnostic_id=diagnostic_id,
        baseline_evaluation_id=baseline.evaluation_id,
        baseline_fingerprint=baseline.fingerprint(),
        agent_identity=AgentIdentity("hold-stub", "0.1"),
        environment_spec=dict(baseline.environment_spec),
        config={},
        budget=_EB(None, 10, None, None, None),
    )
    test = make_null_test()
    state.register_hypothesis(
        Hypothesis(
            hypothesis_id="H-1",
            failure_class="excessive_turnover",
            mechanism="Overreacts to noise bursts.",
            evidence_refs=("E-1",),
            confidence=0.5,
        )
    )
    state.register_test(test)
    state.record_prediction(
        _HP(
            prediction_id="P-1",
            hypothesis_id="H-1",
            test_id=test.test_id,
            predicted_observable="turnover",
            expected_direction="NO_CHANGE",
            rationale="Null keeps mechanics.",
            derivation_method="fixture",
            derivation_version="v1",
        )
    )
    return state


def test_baseline_reference_round_trip(baseline_spec):
    baseline = _baseline_run()
    state = _state_with_baseline_refs(baseline_spec, baseline, "D-SEM-4")
    episode = execute(
        diagnostic_state=state,
        test_id="T-NULL",
        prediction_ids=("P-1",),
        target_agent=HoldAgent(),
        episode_config=make_episode_config(seed=11),
    )
    assert episode.result.baseline_evaluation_id == baseline.evaluation_id
    assert episode.result.baseline_fingerprint == baseline.fingerprint()


def test_unregistered_test_and_prediction_gates(baseline_spec):
    state = make_exec_state(baseline_spec, "D-SEM-5")
    with pytest.raises(ValueError):
        execute(
            diagnostic_state=state,
            test_id="T-GHOST",
            prediction_ids=("P-1",),
            target_agent=HoldAgent(),
            episode_config=make_episode_config(),
        )
    with pytest.raises(ValueError):
        execute(
            diagnostic_state=state,
            test_id="T-NULL",
            prediction_ids=(),
            target_agent=HoldAgent(),
            episode_config=make_episode_config(),
        )
    with pytest.raises(ValueError):
        execute(
            diagnostic_state=state,
            test_id="T-NULL",
            prediction_ids=("P-GHOST",),
            target_agent=HoldAgent(),
            episode_config=make_episode_config(),
        )
    with pytest.raises(TypeError):
        execute(
            diagnostic_state=state,
            test_id="T-NULL",
            prediction_ids=("P-1",),
            target_agent=object(),
            episode_config=make_episode_config(),
        )


def test_budget_exhaustion_prevents_execution(baseline_spec):
    state = make_exec_state(baseline_spec, "D-SEM-6", max_tests=0)
    with pytest.raises(ValueError):
        execute(
            diagnostic_state=state,
            test_id="T-NULL",
            prediction_ids=("P-1",),
            target_agent=HoldAgent(),
            episode_config=make_episode_config(),
        )
    assert state.tests_consumed() == 0


def test_completed_failed_invalid_outcomes(baseline_spec):
    completed = execute(
        diagnostic_state=make_exec_state(baseline_spec, "D-SEM-7a"),
        test_id="T-NULL",
        prediction_ids=("P-1",),
        target_agent=HoldAgent(),
        episode_config=make_episode_config(seed=1),
    )
    assert completed.result.status.value == "COMPLETED"
    assert completed.result.error is None
    assert completed.result.outcome == "COMPLETED"

    failed_state = make_exec_state(baseline_spec, "D-SEM-7b")
    failed = execute(
        diagnostic_state=failed_state,
        test_id="T-NULL",
        prediction_ids=("P-1",),
        target_agent=ExplodingAgent(),
        episode_config=make_episode_config(seed=1),
    )
    assert failed.result.status.value == "FAILED"
    assert failed.result.error
    assert failed.result.measured == ()
    assert len(failed.decision_records) == 1
    assert failed.result.record_fps == tuple(
        r.fingerprint() for r in failed.decision_records
    )

    from evaluation.contracts.diagnostic_tests import DiagnosticTest

    bad = DiagnosticTest(
        test_id="T-BAD",
        description="Names an unsupported intervention.",
        target_failure_classes=("excessive_turnover",),
        intervention={"type": "volatility_oracle_shift", "sigma": 2.0},
        measures=("turnover",),
        expected_discrimination="Nothing honest.",
        estimated_cost=1.0,
    )
    invalid_state = make_exec_state(baseline_spec, "D-SEM-7c", test=bad)
    invalid = execute(
        diagnostic_state=invalid_state,
        test_id="T-BAD",
        prediction_ids=("P-1",),
        target_agent=HoldAgent(),
        episode_config=make_episode_config(seed=1),
    )
    assert invalid.result.status.value == "INVALID"
    assert "unsupported intervention type" in invalid.result.error
    assert invalid.result.measured == ()
    assert invalid.decision_records == ()


def test_malformed_agent_output_becomes_failed_not_silent(baseline_spec):
    state = make_exec_state(baseline_spec, "D-SEM-8")
    episode = execute(
        diagnostic_state=state,
        test_id="T-NULL",
        prediction_ids=("P-1",),
        target_agent=BrokenOutputAgent(),
        episode_config=make_episode_config(seed=1),
    )
    assert episode.result.status.value == "FAILED"
    assert episode.result.error
    assert len(state.test_results) == 1


def test_environment_remains_sole_execution_authority(baseline_spec):
    from environment.indian.information_lookup import InformationLookup

    state = make_exec_state(baseline_spec, "D-SEM-9")
    episode = execute(
        diagnostic_state=state,
        test_id="T-NULL",
        prediction_ids=("P-1",),
        target_agent=BuyOnceAgent(),
        episode_config=make_episode_config(seed=3),
    )
    lookup = InformationLookup(base_dir=".")
    expected_price = lookup.bar_close(
        "nse_equity", {"symbol": "RELIANCE", "series": "EQ"}, "2023-05-15"
    )
    execution = episode.decision_records[0].executions[0]
    assert execution["execution_price"] == expected_price
    # Fee arithmetic is the environment's own (rate-multiplied); the record
    # must carry the env number, compared here up to float association.
    expected_fee = 10.0 * expected_price * 5.0 / 10000.0
    assert execution["transaction_cost"] == pytest.approx(expected_fee)
    assert episode.decision_records[0].transaction_cost == pytest.approx(
        expected_fee
    )
