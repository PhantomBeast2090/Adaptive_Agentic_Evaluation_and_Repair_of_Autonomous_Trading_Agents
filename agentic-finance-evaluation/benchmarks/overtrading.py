"""Controlled overtrading benchmark (M-R5B, additive).

CONTROLLED-KNOWN-MECHANISM: emits a fixed burst of small BUY orders
every session (one per configured name plus a duplicate), ignoring
need, cost accumulation, and regime. Deterministic, E0-native
(TargetObservation only), frozen at creation.
"""

from __future__ import annotations

from typing import Any, Dict, List

from benchmarks.observation import (
    as_dict,
    build_order,
    read_cash,
)
from evaluation.contracts.agent import AgentIdentity

AGENT_ID = "overtrading-benchmark"
AGENT_VERSION = "1.0"

NSE_ASSET_ID = "nse_equity"
NAMES = ("AAA:EQ", "BBB:EQ", "CCC:EQ")
ORDER_QUANTITY = 1.0
CASH_DUST = 1.0
MAX_ORDERS_PER_SESSION = 6


class OvertradingBenchmark:
    """Fixed multi-order burst every session (known flaw)."""

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
        orders.append(
            build_order(NSE_ASSET_ID, NAMES[0], "BUY", ORDER_QUANTITY))
        return orders[:MAX_ORDERS_PER_SESSION]
