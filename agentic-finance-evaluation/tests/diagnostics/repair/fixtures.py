"""Shared builders for E2-F repair tests (no env unless stated).

Unit tests use hand-built frozen artefacts only. Integration tests that
run real E1 validation episodes reuse the SMALL-window baseline config
shape from ``tests.baseline.stubs`` conventions with stub agents defined
locally (a churn agent that actually trades, so turnover is defined).
"""

from evaluation.baseline.config import BaselineConfig
from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.budget import EvaluationBudget
from evaluation.contracts.decision_record import DecisionRecord
from evaluation.contracts.evaluation_state import EvaluationState
from evaluation.baseline.results import BaselineResult
from evaluation.diagnostics.contracts.diagnostic_state import DiagnosticState
from evaluation.diagnostics.contracts.predictions import ExpectedDirection

from ..fixtures import make_hypothesis


def make_repair_baseline(metrics, evaluation_id="B-R", window=None, universe=None):
    from ..execution_fixtures import FULL_UNIVERSE

    window = window or ("2023-05-15", "2023-05-26")
    universe = universe or FULL_UNIVERSE
    agent = AgentIdentity("churn-stub", "0.1")
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
    from evaluation.baseline.metrics import MetricResult

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
            MetricResult(
                name=name,
                value=value,
                unit="ratio",
                derivation="e1.fixture.v1",
            )
            if value is not None
            else MetricResult(
                name=name,
                value=None,
                unit="ratio",
                undefined_reason="no observations in fixture",
                derivation="e1.fixture.v1",
            )
            for name, value in metrics.items()
        ),
        evidence=(),
        evaluation_state=state,
        stopping_reason=None,
        budget_usage={"episodes": 1},
    )


def make_repair_state(baseline, hypotheses=None, diagnostic_id="D-R", budget=None):
    from ..execution_fixtures import HoldAgent

    agent = HoldAgent()
    state = DiagnosticState(
        diagnostic_id=diagnostic_id,
        baseline_evaluation_id=baseline.evaluation_id,
        baseline_fingerprint=baseline.fingerprint(),
        agent_identity=agent.identity,
        environment_spec={"market_fingerprint": "mfp-fixture"},
        config={},
        budget=budget or EvaluationBudget(None, 10, None, None, None),
    )
    for hypothesis in hypotheses or [make_hypothesis()]:
        state.register_hypothesis(hypothesis)
    return state


class ChurnStub:
    """Trades every other decision so turnover is defined and positive."""

    identity = AgentIdentity("churn-stub", "0.1")

    def __init__(self):
        self.calls = 0

    def reset(self):
        self.calls = 0

    def act(self, observation):
        self.calls += 1
        if self.calls % 2 == 1:
            return [
                {
                    "asset_id": "nse_equity",
                    "instrument": "RELIANCE:EQ",
                    "side": "BUY",
                    "quantity": 1.0,
                }
            ]
        return []


class HoldStub:
    """Never trades; used to check inactivity-collapse rejection."""

    identity = AgentIdentity("hold-stub", "0.1")

    def reset(self):
        return None

    def act(self, observation):
        return []
