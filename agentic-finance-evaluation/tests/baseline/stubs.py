"""Local Indian-compatible stub agents for E1 tests.

These implement the E0 ``TargetAgent`` order-list contract against the
Indian multi-asset environment. Legacy US single-asset agents are
deliberately NOT adapted here (D4): no instrument mapping is invented.
"""

from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.oracle import TargetObservation


def _require_observation(observation):
    if not isinstance(observation, TargetObservation):
        raise TypeError(
            "stub agents accept only TargetObservation, "
            f"got {type(observation).__name__}"
        )


class HoldAgent:
    """Submits no orders on any session."""

    identity = AgentIdentity("hold-stub", "0.1")

    def reset(self):
        return None

    def act(self, observation):
        _require_observation(observation)
        return []


class BuyOnceAgent:
    """Buys 10 RELIANCE:EQ on the first decision, then holds."""

    identity = AgentIdentity("buy-once-stub", "0.1")

    def __init__(self):
        self.calls = 0

    def reset(self):
        self.calls = 0

    def act(self, observation):
        _require_observation(observation)
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


class OutsideUniverseAgent:
    """Orders a well-formed instrument outside the configured universe."""

    identity = AgentIdentity("outside-universe-stub", "0.1")

    def reset(self):
        return None

    def act(self, observation):
        _require_observation(observation)
        return [
            {
                "asset_id": "nse_equity",
                "instrument": "INFY:EQ",
                "side": "BUY",
                "quantity": 1.0,
            }
        ]


class ChurnAgent:
    """Alternates BUY/SELL of 1 RELIANCE:EQ every session (reversals)."""

    identity = AgentIdentity("churn-stub", "0.1")

    def __init__(self):
        self.calls = 0

    def reset(self):
        self.calls = 0

    def act(self, observation):
        _require_observation(observation)
        self.calls += 1
        side = "BUY" if self.calls % 2 == 1 else "SELL"
        return [
            {
                "asset_id": "nse_equity",
                "instrument": "RELIANCE:EQ",
                "side": side,
                "quantity": 1.0,
            }
        ]


class BrokenAgent:
    """Returns a malformed non-sequence decision (must fail closed)."""

    identity = AgentIdentity("broken-stub", "0.1")

    def reset(self):
        return None

    def act(self, observation):
        _require_observation(observation)
        return "BUY"


class RecordingAgent(HoldAgent):
    """Records every observation payload it receives (leakage tests)."""

    identity = AgentIdentity("recording-stub", "0.1")

    def __init__(self):
        self.seen = []

    def reset(self):
        self.seen = []

    def act(self, observation):
        _require_observation(observation)
        self.seen.append(observation.to_dict())
        return []


def small_config(evaluation_id, **overrides):
    """Deterministic SMALL-window config dict for E1 tests."""
    from evaluation.baseline.config import BaselineConfig
    from evaluation.contracts.budget import EvaluationBudget

    kwargs = {
        "evaluation_id": evaluation_id,
        "start_date": "2023-05-15",
        "end_date": "2023-05-26",
        "universe": {
            "nse_equity": ["RELIANCE:EQ", "TCS:EQ"],
            "mcx_gold": ["GOLDAUG2023"],
        },
        "budget": EvaluationBudget(10, None, None, None, None),
    }
    kwargs.update(overrides)
    return BaselineConfig(**kwargs)
