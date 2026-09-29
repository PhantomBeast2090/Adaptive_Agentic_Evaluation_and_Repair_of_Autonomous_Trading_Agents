"""Controlled volatility-blind benchmark, synthetic regime (M-R5D, additive).

CONTROLLED-KNOWN-MECHANISM: fixed BUY every session regardless of the
synthetic VIX regime series (calm ~12 vs stress ~30 episodes).
Deterministic, E0-native (TargetObservation only, reads but ignores
the ``indiavix`` slot), frozen at creation. Lets the M-R5 family test
volatility-conditioned repairs without Indian-market runtime cost.
"""

from __future__ import annotations

from typing import Any, Dict, List

from benchmarks.observation import (
    as_dict,
    build_order,
    read_cash,
    read_indicator_close,
)
from evaluation.contracts.agent import AgentIdentity

AGENT_ID = "volatility-blind-synth-benchmark"
AGENT_VERSION = "1.0"

NSE_ASSET_ID = "nse_equity"
INSTRUMENT = "AAA:EQ"
VIX_SLOT = "indiavix"
BUILD_QUANTITY = 2.0
CASH_DUST = 1.0


class VolatilityBlindSynthBenchmark:
    """Fixed buying regardless of VIX regime (known flaw)."""

    identity = AgentIdentity(AGENT_ID, AGENT_VERSION)

    def __init__(self):
        self.calls = 0

    def reset(self):
        self.calls = 0
        return None

    def act(self, observation: Any):
        payload = as_dict(observation)
        self.calls += 1
        _ = read_indicator_close(payload, VIX_SLOT)
        cash = read_cash(payload)
        if cash is None or cash < CASH_DUST:
            return []
        return [build_order(NSE_ASSET_ID, INSTRUMENT, "BUY",
                            BUILD_QUANTITY)]
