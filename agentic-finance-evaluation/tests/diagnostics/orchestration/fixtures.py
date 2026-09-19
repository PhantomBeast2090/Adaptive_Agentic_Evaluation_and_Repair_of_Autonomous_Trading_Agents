"""Shared builders for E2-E orchestration tests.

Light tests use hand-built frozen artefacts only. Heavy tests executing
real episodes wire a real environment spec (for ``resolve_env_config``)
together with a baseline whose config window/universe matches it, plus
agent stubs from ``tests.diagnostics.execution_fixtures``.
"""

import pytest

from environment.indian.environment import IndianMultiAssetEnvironment
from evaluation.baseline.config import BaselineConfig
from evaluation.baseline.metrics import MetricResult
from evaluation.baseline.results import BaselineResult
from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.budget import EvaluationBudget
from evaluation.contracts.decision_record import DecisionRecord
from evaluation.contracts.evaluation_state import EvaluationState
from evaluation.diagnostics.contracts.diagnostic_state import DiagnosticState
from evaluation.diagnostics.orchestration.config import OrchestrationConfig

from ..execution_fixtures import FULL_UNIVERSE, SMALL_ENV_CONFIG
from ..fixtures import make_hypothesis, make_test

SMALL_WINDOW = ("2023-05-15", "2023-05-26")


@pytest.fixture(scope="module")
def real_spec():
    env = IndianMultiAssetEnvironment(dict(SMALL_ENV_CONFIG))
    return env.spec()


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


def make_loop_baseline(
    metrics=None, evaluation_id="B-LOOP", window=None, universe=None
):
    """Frozen BaselineResult whose config window/universe match real data."""
    window = window or SMALL_WINDOW
    universe = universe or FULL_UNIVERSE
    agent = AgentIdentity("hold-stub", "0.1")
    budget = EvaluationBudget(None, 10, None, None, None)
    record = DecisionRecord(
        decision_timestamp=window[0],
        state_fingerprint="fp-fixture-1",
        visible_assets=("NIFTY_50",),
        unavailable_assets=("INDIA_VIX",),
        environment_metadata={"market_fingerprint": "mfp-fixture"},
        portfolio_before={"cash": 100000.0, "total_equity": 100000.0},
        portfolio_after={"cash": 100000.0, "total_equity": 100000.0},
    )
    config = BaselineConfig(
        evaluation_id=evaluation_id,
        start_date=window[0],
        end_date=window[1],
        universe={k: tuple(v) for k, v in universe.items()},
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
            make_metric(name, value)
            for name, value in (metrics or {"turnover": 1.0}).items()
        ),
        evidence=(),
        evaluation_state=state,
        stopping_reason=None,
        budget_usage={"episodes": 1},
    )


def make_loop_state(
    baseline,
    real_spec,
    diagnostic_id="D-LOOP",
    max_tests=10,
    hypotheses=None,
    agent=None,
):
    from ..execution_fixtures import HoldAgent

    agent = agent or HoldAgent()
    state = DiagnosticState(
        diagnostic_id=diagnostic_id,
        baseline_evaluation_id=baseline.evaluation_id,
        baseline_fingerprint=baseline.fingerprint(),
        agent_identity=agent.identity,
        environment_spec=dict(real_spec),
        config={},
        budget=EvaluationBudget(None, max_tests, None, None, None),
    )
    for hypothesis in hypotheses or [make_hypothesis()]:
        state.register_hypothesis(hypothesis)
    return state


def make_loop_config(baseline, agent, **overrides):
    params = {
        "diagnostic_id": "D-LOOP",
        "baseline_evaluation_id": baseline.evaluation_id,
        "baseline_fingerprint": baseline.fingerprint(),
        "max_iterations": 3,
        "seed": 7,
        "agent_id": agent.identity.agent_id,
        "agent_version": agent.identity.version,
    }
    params.update(overrides)
    return OrchestrationConfig(**params)


def make_baseline_config(evaluation_id="B-LOOP"):
    return BaselineConfig(
        evaluation_id=evaluation_id,
        start_date=SMALL_WINDOW[0],
        end_date=SMALL_WINDOW[1],
        universe={k: tuple(v) for k, v in FULL_UNIVERSE.items()},
        budget=EvaluationBudget(None, 10, None, None, None),
    )
