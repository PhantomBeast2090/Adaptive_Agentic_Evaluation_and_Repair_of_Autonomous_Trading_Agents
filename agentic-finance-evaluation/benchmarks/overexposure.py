"""Controlled exposure benchmark (M-R5C, additive).

CONTROLLED-KNOWN-MECHANISM: accumulates a broad multi-name position
every session (fixed BUY on every configured name) with no breadth or
size discipline. Deterministic, E0-native (TargetObservation only),
frozen at creation.
"""

from __future__ import annotations

from typing import Any, Dict, List

from benchmarks.observation import (
    as_dict,
    build_order,
    read_cash,
)
from evaluation.contracts.agent import AgentIdentity

AGENT_ID = "exposure-benchmark"
AGENT_VERSION = "1.0"

NSE_ASSET_ID = "nse_equity"
NAMES = ("AAA:EQ", "BBB:EQ", "CCC:EQ")
ORDER_QUANTITY = 10.0
CASH_DUST = 1.0
MAX_ORDERS_PER_SESSION = 6


class ExposureBenchmark:
    """Unbounded breadth accumulation every session (known flaw)."""

    identity = AgentIdentity(AGENT_ID, AGENT_VERSION)

    def __init__(self):
        self.calls = 0

    def reset(self):
        self.calls = 0
        return None

    def act(self, observation: Any):
        payload = as_dict(observation)
        self.calls += 1
        cash = read_cash(payload)
        if cash is None or cash < CASH_DUST:
            return []
        orders: List[Dict[str, Any]] = []
        for name in NAMES:
            orders.append(
                build_order(NSE_ASSET_ID, name, "BUY", ORDER_QUANTITY))
        return orders[:MAX_ORDERS_PER_SESSION]
