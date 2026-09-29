"""Canonical loss-chasing benchmark: loss-chasing-benchmark@1.0.

CONTROLLED-KNOWN-MECHANISM (M-R3 repair benchmark — engineering/causal
validation of the repair architecture, NOT natural-market discovery).

Deliberate known flaw: tracks own previous portfolio total value; after
each consecutive decline, scales the BUY quantity as
``NORMAL_QUANTITY * 2**consecutive_losses`` capped only by affordability.
Normal behaviour (no recent loss): fixed BUY of NORMAL_QUANTITY when
affordable. The pre-registered repair cap equals NORMAL_QUANTITY, so the
repair binds ONLY escalation, never normal flow.

E0 contract: TargetObservation only (cash, total_equity, positions,
one NSE slot close for affordability checks). Deterministic given the
observation sequence; episode-local counters restored by reset().
Frozen at creation; any constant change is a new version.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from benchmarks.observation import (
    as_dict,
    build_order,
    position_key,
    read_cash,
    read_indicator_close,
    read_positions,
)
from evaluation.contracts.agent import AgentIdentity

AGENT_ID = "loss-chasing-benchmark"
AGENT_VERSION = "1.0"

NSE_ASSET_ID = "nse_equity"
INSTRUMENT = "RELIANCE:EQ"
VIX_SLOT = "indiavix"
NORMAL_QUANTITY = 5.0
CASH_DUST = 1.0
MAX_ORDERS_PER_SESSION = 3


class LossChasingBenchmark:
    """Deterministic post-loss quantity escalation (known flaw)."""

    identity = AgentIdentity(AGENT_ID, AGENT_VERSION)

    def __init__(self):
        self.calls = 0
        self.consecutive_losses = 0
        self.previous_value: Optional[float] = None

    def reset(self):
        self.calls = 0
        self.consecutive_losses = 0
        self.previous_value = None
        return None

    def _total_value(self, payload: Dict[str, Any]) -> Optional[float]:
        portfolio = payload.get("portfolio", {})
        value = portfolio.get("total_equity") if isinstance(
            portfolio, dict) else None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            return None
        return number

    def _price(self, payload: Dict[str, Any]) -> Optional[float]:
        market = payload.get("market", {})
        if not isinstance(market, dict):
            return None
        for key in sorted(market):
            if key.startswith("nse_equity:"):
                price = read_indicator_close(payload, key)
                if price is not None and price > 0:
                    return price
        return None

    def act(self, observation: Any):
        payload = as_dict(observation)
        self.calls += 1
        cash = read_cash(payload)
        if cash is None or cash < CASH_DUST:
            return []
        current = self._total_value(payload)
        if (
            current is not None
            and self.previous_value is not None
            and current < self.previous_value
        ):
            self.consecutive_losses += 1
        elif current is not None:
            self.consecutive_losses = 0
        if current is not None:
            self.previous_value = current
        price = self._price(payload)
        if price is None:
            return []
        if self.consecutive_losses > 0:
            quantity = min(NORMAL_QUANTITY * (2 ** self.consecutive_losses),
                           cash / price)
        else:
            quantity = min(NORMAL_QUANTITY, cash / price)
        if quantity <= 0:
            return []
        return [build_order(NSE_ASSET_ID, INSTRUMENT, "BUY", quantity)][
            :MAX_ORDERS_PER_SESSION
        ]
