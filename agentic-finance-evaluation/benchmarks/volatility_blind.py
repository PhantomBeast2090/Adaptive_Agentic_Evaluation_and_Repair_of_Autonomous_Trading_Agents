"""Canonical volatility-blind benchmark: volatility-blind-benchmark@1.0.

CONTROLLED-KNOWN-MECHANISM (M-R2 repair benchmark — engineering/causal
validation of the repair architecture, NOT natural-market discovery).

Deliberate known flaw: issues a fixed BUY order every session cash
allows, completely ignoring the VIX regime — including sustained
high-volatility episodes where accumulation is the documented failure.
Normal (LOW/MID) behaviour is intentionally identical (steady buying) so
the repair's scope safety is testable: a regime-scoped hold_all must
alter HIGH sessions only.

E0 contract: TargetObservation only (indiavix slot, cash, positions).
Deterministic. Frozen at creation; any constant change is a new version.
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

AGENT_ID = "volatility-blind-benchmark"
AGENT_VERSION = "1.0"

NSE_ASSET_ID = "nse_equity"
INSTRUMENT = "RELIANCE:EQ"
VIX_SLOT = "indiavix"
BUILD_QUANTITY = 1.0
CASH_DUST = 1.0


class VolatilityBlindBenchmark:
    """Fixed buying regardless of volatility regime (known flaw)."""

    identity = AgentIdentity(AGENT_ID, AGENT_VERSION)

    def __init__(self):
        self.calls = 0

    def reset(self):
        self.calls = 0
        return None

    def act(self, observation: Any):
        payload = as_dict(observation)
        self.calls += 1
        # Deliberately reads VIX only to prove nothing depends on it.
        _ = read_indicator_close(payload, VIX_SLOT)
        cash = read_cash(payload)
        if cash is None or cash < CASH_DUST:
            return []
        return [build_order(NSE_ASSET_ID, INSTRUMENT, "BUY",
                            BUILD_QUANTITY)]
