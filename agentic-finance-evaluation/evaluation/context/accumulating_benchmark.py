"""Accumulating threshold benchmark: dual-guard E4 delivery instrument.

Identical frozen VolThreshold base policy (same constants, same readers
as the frozen benchmark), plus two mechanism-keyed contextual guards
with genuinely orthogonal geometry:

* turnover guard (``failure_mechanism == "turnover"``): skip LOW-regime
  BUY orders for already-held names — throttles accumulation *depth*,
  mirroring the E2-F order-cap correction.
* exposure guard (``failure_mechanism == "exposure"``): when the
  portfolio already holds any position, skip BUY orders for names with
  zero position — throttles accumulation *breadth*, mirroring the E2-F
  breadth-cap correction. A flat portfolio admits all base-policy
  orders, so the guard can never manufacture permanent inactivity.

Any other mechanism, malformed entry, or empty context leaves the base
policy bit-identical. Whether either guard improves trading outcomes is
an empirical E4-F question, not a construction claim.

Information boundary: TargetObservation only. ``reset()`` clears
episode-local call counts and preserves learned context (E0
reset/adapt separation).
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple

from benchmarks.observation import (
    as_dict,
    build_order,
    position_key,
    read_cash,
    read_indicator_close,
    read_positions,
)
from benchmarks.volatility_threshold import (
    BUILD_QUANTITY,
    CASH_DUST,
    MAX_ORDERS_PER_SESSION,
    NSE_ASSET_ID,
    NSE_EQUITY_NAMES,
    REDUCE_QUANTITY,
    VIX_HIGH,
    VIX_LOW,
    VIX_SLOT,
)
from evaluation.contracts.agent import AgentIdentity

AGENT_ID = "accumulating-threshold-benchmark"
AGENT_VERSION = "1.0"

TURNOVER_MECHANISM = "turnover"
EXPOSURE_MECHANISM = "exposure"

_REQUIRED_ENTRY_KEYS = (
    "context_id",
    "failure_mechanism",
    "corrective_principle",
)


class AccumulatingThresholdBenchmark:
    """VIX-threshold strategy with two validated-context guards."""

    identity = AgentIdentity(AGENT_ID, AGENT_VERSION)

    def __init__(self):
        self.calls = 0
        self.learned_contexts: Tuple[Mapping[str, Any], ...] = ()

    def reset(self):
        self.calls = 0
        return None

    def adapt(self, intervention: Mapping[str, Any]) -> None:
        """Accept one delivery payload of validated learned context."""
        if not isinstance(intervention, Mapping):
            raise TypeError("intervention must be a mapping")
        entries = intervention.get("entries", ())
        if isinstance(entries, str) or not isinstance(entries, (tuple, list)):
            raise TypeError("intervention entries must be a tuple/list")
        if not tuple(entries):
            raise ValueError(
                "intervention entries must be non-empty: empty "
                "deliveries fail closed"
            )
        cleaned = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise TypeError("context entries must be mappings")
            for key in _REQUIRED_ENTRY_KEYS:
                value = entry.get(key)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(
                        f"context entry lacks {key!r}: refusing "
                        "malformed knowledge"
                    )
            cleaned.append(dict(entry))
        self.learned_contexts = self.learned_contexts + tuple(cleaned)

    def _guard_active(self, mechanism: str) -> bool:
        return any(
            entry.get("failure_mechanism") == mechanism
            for entry in self.learned_contexts
            if isinstance(entry, Mapping)
        )

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
        turnover_guard = self._guard_active(TURNOVER_MECHANISM)
        exposure_guard = self._guard_active(EXPOSURE_MECHANISM)
        positions = (
            read_positions(payload)
            if (turnover_guard or exposure_guard) else {}
        )
        held = {
            name for name in NSE_EQUITY_NAMES
            if positions.get(position_key(NSE_ASSET_ID, name), 0.0) > 0
        }
        orders = []
        for name in NSE_EQUITY_NAMES:
            if turnover_guard and name in held:
                continue
            if exposure_guard and held and name not in held:
                continue
            orders.append(
                build_order(NSE_ASSET_ID, name, "BUY", BUILD_QUANTITY)
            )
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
