"""Canonical volatility-threshold benchmark: volatility-threshold-benchmark@1.0.

The only core repairable E3 benchmark. A rule-based India VIX threshold
strategy, specified independently of any downstream evaluation machinery:

* LOW VIX (prior-session India VIX close below 15.0): diversified
  accumulation — one BUY order per configured NSE equity name, fixed
  quantity each. Per-name allocation is the strategy itself: steady
  exposure building spread across the configured names in calm regimes.
* MID VIX (15.0 through 25.0 inclusive): hold. Boundary equality belongs
  to MID by documented tie rule.
* HIGH VIX (above 25.0): reduce toward floor zero — one SELL order per
  held configured name, up to a fixed quantity each.
* Missing or unavailable VIX (non-AVAILABLE slot, empty or non-numeric
  close): hold. Missing information is never imputed or forward-filled.

Thresholds 15.0/25.0 are a pre-existing repository convention
(legacy control rules and scenario configuration), recorded here as an
uncalibrated design convention — not estimated, not tuned, not fitted
to any experimental window.

Information boundary: TargetObservation only (India VIX close from the
``indiavix`` slot after an AVAILABLE check; cash and positions from the
portfolio block). No raw environment state, no evaluator internals, no
diagnostic state, no future data, no direct environment access. Only
configured-universe instruments are ever ordered. Episode-local call
count restored by reset(). Deterministic given identical observations.
"""

from __future__ import annotations

from typing import Any, Dict, List

from benchmarks.observation import (
    as_dict,
    build_order,
    position_key,
    read_cash,
    read_indicator_close,
    read_positions,
)
from evaluation.contracts.agent import AgentIdentity

AGENT_ID = "volatility-threshold-benchmark"
AGENT_VERSION = "1.0"

# Frozen E3-C universe (mirrored in benchmarks/manifest.yaml).
NSE_EQUITY_NAMES = ("RELIANCE:EQ", "TCS:EQ")
NSE_ASSET_ID = "nse_equity"

# VIX regime convention (uncalibrated; see module docstring).
VIX_LOW = 15.0
VIX_HIGH = 25.0
VIX_SLOT = "indiavix"

# Frozen policy constants (E3-C design conventions, not fitted values).
BUILD_QUANTITY = 1.0
REDUCE_QUANTITY = 5.0
CASH_DUST = 1.0
MAX_ORDERS_PER_SESSION = 3


class VolatilityThresholdBenchmark:
    """Rule-based VIX-threshold strategy over configured NSE equities."""

    identity = AgentIdentity(AGENT_ID, AGENT_VERSION)

    def __init__(self):
        self.calls = 0

    def reset(self):
        self.calls = 0
        return None

    def act(self, observation: Any):
        payload = as_dict(observation)
        self.calls += 1
        vix = read_indicator_close(payload, VIX_SLOT)
        if vix is None:
            return []
        if vix < VIX_LOW:
            return self._build(payload)
        if vix > VIX_HIGH:
            return self._reduce(payload)
        return []

    def _build(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        cash = read_cash(payload)
        if cash is None or cash < CASH_DUST:
            return []
        orders = [
            build_order(NSE_ASSET_ID, name, "BUY", BUILD_QUANTITY)
            for name in NSE_EQUITY_NAMES
        ]
        return orders[:MAX_ORDERS_PER_SESSION]

    def _reduce(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        positions = read_positions(payload)
        orders = []
        for name in NSE_EQUITY_NAMES:
            quantity = positions.get(position_key(NSE_ASSET_ID, name), 0.0)
            if quantity > 0:
                orders.append(
                    build_order(
                        NSE_ASSET_ID, name, "SELL",
                        min(quantity, REDUCE_QUANTITY),
                    )
                )
        return orders[:MAX_ORDERS_PER_SESSION]
