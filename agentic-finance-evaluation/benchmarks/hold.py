"""Canonical hold benchmark: hold-benchmark@1.0.

Evaluator-mechanics and provenance control. Submits no orders on any
session. Deterministic, stateless, resettable. TargetObservation only.
"""

from __future__ import annotations

from typing import Any

from benchmarks.observation import as_dict
from evaluation.contracts.agent import AgentIdentity

AGENT_ID = "hold-benchmark"
AGENT_VERSION = "1.0"


class HoldBenchmark:
    """Never trades. The null target for evaluator-mechanics checks."""

    identity = AgentIdentity(AGENT_ID, AGENT_VERSION)

    def reset(self):
        return None

    def act(self, observation: Any):
        as_dict(observation)
        return []
