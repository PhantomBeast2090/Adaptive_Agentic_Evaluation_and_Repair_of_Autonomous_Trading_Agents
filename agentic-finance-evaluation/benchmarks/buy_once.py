"""Canonical buy-once benchmark: buy-once-benchmark@1.0.

Execution-path control. Submits exactly one predetermined valid
configured-universe NSE equity order (BUY RELIANCE:EQ, quantity 10) at
the first eligible decision of an episode, then holds. Deterministic
episode counter restored by reset(). TargetObservation only.
"""

from __future__ import annotations

from typing import Any

from benchmarks.observation import as_dict, build_order
from evaluation.contracts.agent import AgentIdentity

AGENT_ID = "buy-once-benchmark"
AGENT_VERSION = "1.0"

ASSET_ID = "nse_equity"
INSTRUMENT = "RELIANCE:EQ"
SIDE = "BUY"
QUANTITY = 10.0


class BuyOnceBenchmark:
    """One scripted opening trade per episode, then holds."""

    identity = AgentIdentity(AGENT_ID, AGENT_VERSION)

    def __init__(self):
        self.calls = 0

    def reset(self):
        self.calls = 0
        return None

    def act(self, observation: Any):
        as_dict(observation)
        self.calls += 1
        if self.calls == 1:
            return [
                build_order(ASSET_ID, INSTRUMENT, SIDE, QUANTITY)
            ]
        return []
