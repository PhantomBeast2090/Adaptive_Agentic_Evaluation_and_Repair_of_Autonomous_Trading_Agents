"""Lifecycle pure helpers: deltas, matrices, builders, policy seam guards."""

import pytest

from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.budget import EvaluationBudget
from evaluation.diagnostics.contracts.diagnostic_state import DiagnosticState
from experiments.harness.errors import ProtocolAmbiguityError
from experiments.harness.lifecycle import (
    baseline_config_for,
    build_prediction_matrix,
    commit_predictions,
    diagnostic_state_for,
    metric_map,
    paired_deltas,
    register_pool_tests,
)

from .fixtures import DIAG, HELD, make_baseline, make_config


def test_paired_deltas_preserve_none_without_imputation():
    deltas = paired_deltas(
        {"turnover": 2.0, "sharpe_per_session": None},
        {"turnover": 1.0},
    )
    assert deltas["turnover"] == {
        "reference": 2.0,
        "validation": 1.0,
        "delta": -1.0,
    }
    assert deltas["sharpe_per_session"]["delta"] is None
    assert deltas["sharpe_per_session"]["reference"] is None


def test_metric_map_rejects_non_baselines():
    with pytest.raises(TypeError):
        metric_map({"turnover": 1.0})


def test_prediction_matrix_frozen_content():
    matrix = build_prediction_matrix()
    assert ("H-turnover", "T-uni-tcs", "turnover", "DECREASE",
            "fewer names to accumulate, less order flow") in matrix
    assert ("H-turnover", "T-exp-narrow", "turnover", "DECREASE",
            "narrower universe admits less order flow") in matrix
    assert ("H-exposure", "T-exp-narrow", "gross_exposure_max",
            "DECREASE",
            "single-name universe caps accumulation breadth and peak "
            "exposure") in matrix
    assert ("H-exposure", "T-uni-tcs", "gross_exposure_max",
            "DECREASE",
            "fewer names to accumulate, lower peak exposure") in matrix
    # Promotion set is exactly the two discriminating breadth rows:
    # no null/no-change exposure rows may manufacture support.
    assert sorted(
        row[1] for row in matrix if row[0] == "H-exposure"
    ) == ["T-exp-narrow", "T-uni-tcs"]
    assert all(
        row[2] == "gross_exposure_max" and row[3] == "DECREASE"
        for row in matrix if row[0] == "H-exposure"
    )
    assert {row[0] for row in matrix} == {"H-turnover", "H-exposure"}
    assert "H-concentration" not in str(matrix)


def test_commit_predictions_unknown_hypothesis_fails_closed():
    state = DiagnosticState(
        diagnostic_id="D",
        baseline_evaluation_id="B",
        baseline_fingerprint="fp",
        agent_identity=AgentIdentity("a", "1"),
        environment_spec={"market_fingerprint": "m"},
        config={},
        budget=EvaluationBudget(None, 10, None, None, None),
    )
    with pytest.raises(ProtocolAmbiguityError):
        commit_predictions(state, "H-nope")


def test_register_pool_unknown_test_fails_closed():
    from evaluation.contracts.diagnostic_tests import DiagnosticTest

    state = DiagnosticState(
        diagnostic_id="D",
        baseline_evaluation_id="B",
        baseline_fingerprint="fp",
        agent_identity=AgentIdentity("a", "1"),
        environment_spec={"market_fingerprint": "m"},
        config={},
        budget=EvaluationBudget(None, 10, None, None, None),
    )
    with pytest.raises(ProtocolAmbiguityError):
        register_pool_tests(state, {"T-nope": {"intervention": {}}})


def test_config_builders_pure_and_frozen():
    config = make_config()
    baseline_cfg = baseline_config_for(config, DIAG, "E-1")
    assert baseline_cfg.start_date == "2023-05-15"
    assert baseline_cfg.transaction_cost_bps == 5.0
    assert baseline_cfg.seed == 7
    baseline = make_baseline("B", DIAG, {"turnover": 1.0})
    agent = AgentIdentity("bench", "1.0")
    state = diagnostic_state_for(config, baseline, agent, "D-1")
    assert state.diagnostic_id == "D-1"
    assert state.budget_usage() == {"tests": 0}


def test_diagnose_rejects_unknown_policy():
    from experiments.harness.lifecycle import diagnose

    with pytest.raises(ValueError):
        diagnose(
            state=None, baseline=None, target_agent=None,
            policy="clever", fixed_sequence=(), seed=None,
        )
