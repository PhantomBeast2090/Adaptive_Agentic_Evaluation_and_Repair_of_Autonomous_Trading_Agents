"""Multi-asset choice agent (G1 behavioural-support milestone).

Subclass of the frozen-behaviour ChoiceAccumulator v1.1: inherits VIX
regimes, trend filter, affordability sizing, staged exits, cash pause,
exposure/concentration ladder. Adds exactly ONE mechanism:

Cross-asset rotation: when the names-held cap binds and an unheld
candidate's trend exceeds the weakest held name's trend by at least
ROTATION_EDGE, SELL the full weakest position and BUY the candidate.
Rationale: standard portfolio rebalancing toward momentum; creates
same-session SELL+BUY overlap and exit/entry pairs deterministically.

Deterministic, CPU-only, fingerprintable, PIT-safe (own-observation
buffers only), order-list contract. No stochasticity/LLM/learning.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

from agents.choice.policy import (
    INSTRUMENTS as _V11_INSTRUMENTS,
    NSE_ASSET_ID,
    ChoiceAccumulator,
    _slot_close,
    build_order,
    position_key,
)

G1_INSTRUMENTS = ("YESBANK:EQ", "ICICIBANK:EQ", "RELIANCE:EQ", "SBIN:EQ",
                  "INFY:EQ", "TCS:EQ")
G1_AGENT_ID = "multi-asset-choice"
G1_AGENT_VERSION = "1.0"

# Rotation edge (trend differential favouring the candidate). Round,
# conservative, pre-registered; not fitted to any outcome.
ROTATION_EDGE = 0.02
G1_DEFAULTS = {"rotation_edge": ROTATION_EDGE}

from evaluation.contracts.agent import AgentIdentity


class MultiAssetChoice(ChoiceAccumulator):
    """Six-name rotation-augmented accumulator (G1)."""

    identity = AgentIdentity(G1_AGENT_ID, G1_AGENT_VERSION)

    def __init__(self, config: Mapping[str, Any] | None = None):
        cfg = dict(config or {})
        instruments = cfg.pop("instruments", None)
        rotation = {k: cfg.pop(k) for k in list(cfg) if k in G1_DEFAULTS}
        super().__init__(cfg, policy_version="1.1")
        self.params.update({**G1_DEFAULTS, **rotation})
        # Base __init__ stamps choice-accumulator@1.1; restore G1 identity.
        self.identity = AgentIdentity(G1_AGENT_ID, G1_AGENT_VERSION)
        names = list(instruments) if instruments else list(G1_INSTRUMENTS)
        self.names: tuple = tuple(names)

    def _remember(self, payload: Mapping[str, Any]) -> None:
        ts = payload.get("decision_timestamp")
        for name in self.names:
            close = _slot_close(payload, f"{NSE_ASSET_ID}:{name}")
            if close is None or not isinstance(ts, str):
                continue
            buf = self._closes.setdefault(name, [])
            if buf and buf[-1][0] == ts:
                continue
            buf.append((ts, close))
        if isinstance(ts, str):
            from agents.choice.policy import _pfolio_number
            cash = _pfolio_number(payload, "cash")
            equity = _pfolio_number(payload, "total_equity")
            if cash is not None and equity is not None:
                if not self._pfhist or self._pfhist[-1][0] != ts:
                    self._pfhist.append((ts, cash, equity))

    def _trend(self, name: str) -> Any:
        lookback = int(self.params["trend_lookback"])
        buf = self._closes.get(name, [])
        if len(buf) <= lookback:
            return None
        old = buf[-1 - lookback][1]
        new = buf[-1][1]
        if old == 0:
            return None
        return (new - old) / old

    def _reduce_all(self, positions: Mapping[str, float]
                    ) -> List[Dict[str, Any]]:
        orders = []
        for name in self.names:
            held = positions.get(position_key(NSE_ASSET_ID, name), 0.0)
            if held > 0:
                orders.append(build_order(
                    NSE_ASSET_ID, name, "SELL",
                    min(held, float(self.params["sell_q"]))))
        return orders

    def _flatten(self, positions: Mapping[str, float]
                 ) -> List[Dict[str, Any]]:
        orders = []
        for name in self.names:
            held = positions.get(position_key(NSE_ASSET_ID, name), 0.0)
            if held > 0:
                orders.append(build_order(NSE_ASSET_ID, name, "SELL", held))
        return orders

    def _trim(self, positions: Mapping[str, float]
              ) -> List[Dict[str, Any]]:
        orders = []
        for name in self.names:
            held = positions.get(position_key(NSE_ASSET_ID, name), 0.0)
            if held > 0:
                orders.append(build_order(NSE_ASSET_ID, name, "SELL",
                                          min(held, 1.0)))
        return orders

    def _accumulate(self, payload: Mapping[str, Any], cash: float,
                    positions: Mapping[str, float]) -> List[Dict[str, Any]]:
        orders: List[Dict[str, Any]] = []
        v11 = self.policy_version == "1.1"
        exposure = None
        equity = None
        if v11:
            from agents.choice.policy import _pfolio_number
            exposure = _pfolio_number(payload, "exposure")
            equity = _pfolio_number(payload, "total_equity")
        names_held = sum(
            1 for n in self.names
            if positions.get(position_key(NSE_ASSET_ID, n), 0.0) > 0)
        capped = names_held >= int(self.params["max_names_held"])
        weakest = self._weakest_held(positions) if capped else (None, None)
        for name in self.names:
            held = positions.get(position_key(NSE_ASSET_ID, name), 0.0)
            trend = self._trend(name)
            if held > 0 and trend is not None and trend < float(
                    self.params["trend_sell"]):
                orders.append(build_order(
                    NSE_ASSET_ID, name, "SELL",
                    min(held, float(self.params["sell_q"]))))
                continue
            if trend is None or trend <= float(self.params["trend_min"]):
                continue
            close = _slot_close(payload, f"{NSE_ASSET_ID}:{name}")
            if close is None:
                continue
            if held * close >= float(self.params["max_name_cost"]):
                continue
            if cash < float(self.params["cash_dust"]):
                continue
            if held == 0 and capped:
                # Rotation: replace weakest held name on strict edge.
                weak_name, weak_trend = weakest
                if weak_name is None or weak_trend is None:
                    continue
                if trend - weak_trend < float(
                        self.params.get("rotation_edge", ROTATION_EDGE)):
                    continue
                orders.append(build_order(
                    NSE_ASSET_ID, weak_name, "SELL",
                    positions.get(
                        position_key(NSE_ASSET_ID, weak_name), 0.0)))
                names_held -= 1
            qty = self._size_qty(held, close, cash)
            if v11:
                if exposure is not None and exposure >= float(
                        self.params["exp_tier_halt"]):
                    continue
                if equity and equity > 0:
                    share = held * close / equity
                    if share >= float(self.params["conc_cap"]):
                        qty = min(qty, 1)
                if held == 0 and exposure is not None and exposure >= float(
                        self.params["exp_tier_full"]):
                    qty = min(qty, 1)
            orders.append(build_order(NSE_ASSET_ID, name, "BUY", qty))
            names_held += 1 if held == 0 else 0
        return orders

    def _weakest_held(self, positions: Mapping[str, float]):
        worst = (None, None)
        for name in self.names:
            if positions.get(position_key(NSE_ASSET_ID, name), 0.0) <= 0:
                continue
            trend = self._trend(name)
            if trend is None:
                continue
            if worst[1] is None or trend < worst[1]:
                worst = (name, trend)
        return worst
