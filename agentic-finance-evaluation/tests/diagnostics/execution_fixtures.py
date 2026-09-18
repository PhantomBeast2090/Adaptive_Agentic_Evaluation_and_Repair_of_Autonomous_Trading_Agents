"""Shared builders for E2-B execution tests (deterministic, no LLM)."""

import pytest

from environment.indian.environment import IndianMultiAssetEnvironment
from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.budget import EvaluationBudget
from evaluation.contracts.diagnostic_tests import DiagnosticTest
from evaluation.contracts.hypotheses import Hypothesis
from evaluation.contracts.oracle import TargetObservation
from evaluation.diagnostics.contracts.diagnostic_state import DiagnosticState
from evaluation.diagnostics.contracts.predictions import HypothesisPrediction
from evaluation.diagnostics.execution.episode import DiagnosticEpisodeConfig

SMALL_ENV_CONFIG = {
    "strict_pit": True,
    "vintage_policy": "explicit",
    "transaction_cost_bps": 5.0,
    "initial_cash": 100000.0,
    "start_date": "2023-05-15",
    "end_date": "2023-05-26",
    "universe": {
        "nse_equity": ["RELIANCE:EQ", "TCS:EQ"],
        "mcx_gold": ["GOLDAUG2023"],
    },
}

FULL_UNIVERSE = {
    "nse_equity": ["RELIANCE:EQ", "TCS:EQ"],
    "mcx_gold": ["GOLDAUG2023"],
}


class HoldAgent:
    identity = AgentIdentity("hold-stub", "0.1")

    def reset(self):
        return None

    def act(self, observation):
        if not isinstance(observation, TargetObservation):
            raise TypeError("stub accepts only TargetObservation")
        return []


class BuyOnceAgent:
    identity = AgentIdentity("buy-once-stub", "0.1")

    def __init__(self):
        self.calls = 0

    def reset(self):
        self.calls = 0

    def act(self, observation):
        if not isinstance(observation, TargetObservation):
            raise TypeError("stub accepts only TargetObservation")
        self.calls += 1
        if self.calls == 1:
            return [
                {
                    "asset_id": "nse_equity",
                    "instrument": "RELIANCE:EQ",
                    "side": "BUY",
                    "quantity": 10.0,
                }
            ]
        return []


class BrokenOutputAgent:
    identity = AgentIdentity("broken-stub", "0.1")

    def reset(self):
        return None

    def act(self, observation):
        return "BUY"


class ExplodingAgent:
    identity = AgentIdentity("exploding-stub", "0.1")

    def __init__(self):
        self.calls = 0

    def reset(self):
        self.calls = 0

    def act(self, observation):
        self.calls += 1
        if self.calls >= 2:
            raise RuntimeError("simulated mid-episode agent failure")
        return []


class OutsideUniverseAgent:
    identity = AgentIdentity("outside-stub", "0.1")

    def reset(self):
        return None

    def act(self, observation):
        return [
            {
                "asset_id": "nse_equity",
                "instrument": "INFY:EQ",
                "side": "BUY",
                "quantity": 1.0,
            }
        ]


class RecordingAgent:
    identity = AgentIdentity("recording-stub", "0.1")

    def __init__(self):
        self.seen = []

    def reset(self):
        self.seen = []

    def act(self, observation):
        if not isinstance(observation, TargetObservation):
            raise TypeError("stub accepts only TargetObservation")
        self.seen.append(observation.to_dict())
        return []


@pytest.fixture(scope="module")
def baseline_spec():
    env = IndianMultiAssetEnvironment(dict(SMALL_ENV_CONFIG))
    return env.spec()


def make_null_test(test_id="T-NULL"):
    return DiagnosticTest(
        test_id=test_id,
        description="Control replay under baseline market conditions.",
        target_failure_classes=("excessive_turnover",),
        intervention={"type": "null_intervention"},
        measures=("turnover", "inactivity_rate"),
        expected_discrimination="Reproduces baseline mechanics.",
        estimated_cost=1.0,
    )


def make_cost_test(test_id="T-COST", multiplier=5.0):
    return DiagnosticTest(
        test_id=test_id,
        description="Shift transaction costs for one replay.",
        target_failure_classes=("excessive_turnover",),
        intervention={"type": "transaction_cost_shift", "multiplier": multiplier},
        measures=("turnover", "transaction_cost_total"),
        expected_discrimination="Cost-sensitive turnover collapses.",
        estimated_cost=2.0,
    )


def make_exec_state(
    spec,
    diagnostic_id="D-EXE",
    test=None,
    max_tests=10,
):
    test = test or make_null_test()
    state = DiagnosticState(
        diagnostic_id=diagnostic_id,
        baseline_evaluation_id="B-EXE",
        baseline_fingerprint="bfp-exe",
        agent_identity=HoldAgent.identity,
        environment_spec=dict(spec),
        config={},
        budget=EvaluationBudget(None, max_tests, None, None, None),
    )
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
        HypothesisPrediction(
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


def make_episode_config(seed=7, universe=None, start="2023-05-15", end="2023-05-26"):
    return DiagnosticEpisodeConfig(
        start_date=start,
        end_date=end,
        universe=dict(universe or FULL_UNIVERSE),
        seed=seed,
    )
