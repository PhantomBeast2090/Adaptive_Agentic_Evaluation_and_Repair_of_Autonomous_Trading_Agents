"""ChoiceAccumulator policy agent (F0 behavioural-diversity milestone).

Deterministic, rule-based, fully reproducible multi-action policy over
frozen Indian-market microstructure. Reads ONLY TargetObservation
slots available at decision time (t-1 observation-lag closes, cash,
positions); keeps an own-observation close buffer for trend rules
(stores past observations only — PIT-safe by construction, cleared on
reset). Emits E0 order lists; never touches OraclePacket, MemoryStore,
or validation machinery.

FROZEN POLICY CONSTANTS (F0): recorded verbatim in configs/
choice_agent/f0.yaml and every F0 manifest. Not tuned against any
outcome. Rationale per rule is documented below (FinRL-style
precedents); no rule targets a known E5A result.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from benchmarks.observation import (
    as_dict,
    build_order,
    position_key,
    read_cash,
    read_indicator_close,
    read_positions,
)
from evaluation.contracts.agent import AgentIdentity

AGENT_ID = "choice-accumulator"
AGENT_VERSION = "1.0"

# -- Frozen F0 policy constants (see configs/choice_agent/f0.yaml) --------
# VIX regime convention inherited from the E5A benchmark (not fitted).
VIX_LOW = 15.0
VIX_HIGH = 25.0
VIX_SLOT = "indiavix"
# Trend filter: 5-session own-close return; BUY only above TREND_MIN
# (FinRL-turbulence-gate pattern: halt accumulation into free fall).
TREND_LOOKBACK = 5
TREND_MIN = -0.03
TREND_SELL = -0.08
# Sizing (integer shares; NSE cash-market plausible).
BUY_Q_FULL = 2
BUY_Q_SMALL = 1
CASH_FULL = 20000.0
SELL_Q = 2
# Exposure/cash constraints.
INSTRUMENTS = ("RELIANCE:EQ", "TCS:EQ", "INFY:EQ")
NSE_ASSET_ID = "nse_equity"
MAX_NAMES_HELD = 3
MAX_NAME_COST = 60000.0
CASH_DUST = 1000.0
MAX_ORDERS_PER_SESSION = 3

# Transaction-rate mirror of the frozen environment (5 bps both sides;
# environment/indian/portfolio.py). Used only for affordability
# arithmetic, never fitted.
TXN_RATE = 0.0005

# Effective-parameter table. F0 runs use these verbatim; F0R overrides
# are recorded in configs/choice_agent/f0r.yaml with rationale.
DEFAULTS = {
    "vix_low": VIX_LOW,
    "vix_high": VIX_HIGH,
    "trend_lookback": TREND_LOOKBACK,
    "trend_min": TREND_MIN,
    "trend_sell": TREND_SELL,
    "sizing_mode": "fixed_cash",
    "buy_q_full": BUY_Q_FULL,
    "buy_q_small": BUY_Q_SMALL,
    "cash_full": CASH_FULL,
    "sell_q": SELL_Q,
    "max_names_held": MAX_NAMES_HELD,
    "max_name_cost": MAX_NAME_COST,
    "cash_dust": CASH_DUST,
    "max_orders_per_session": MAX_ORDERS_PER_SESSION,
}


def _slot_close(payload: Mapping[str, Any], slot_key: str
                ) -> Optional[float]:
    """Read one equity/indicator close via the shared AVAILABLE-checked
    reader (None on missing/unavailable — never imputed)."""
    return read_indicator_close(payload, slot_key)


class ChoiceAccumulator:
    """Deterministic regime-gated accumulator with exits."""

    identity = AgentIdentity(AGENT_ID, AGENT_VERSION)

    def __init__(self, config: Mapping[str, Any] | None = None):
        """Optional overrides (F0-repeat); defaults are the frozen F0
        constants above. Effective constants are fingerprinted into
        every experiment manifest; F0 traces remain reproducible via
        defaults."""
        cfg = dict(config or {})
        unknown = set(cfg) - set(DEFAULTS)
        if unknown:
            raise ValueError(f"unknown policy keys: {sorted(unknown)}")
        self.params = {**DEFAULTS, **cfg}
        self.calls = 0
        self.learned_contexts: List[Any] = []
        # Own-observation history: {slot_key: [(timestamp, close)]}.
        self._closes: Dict[str, List[Any]] = {}

    def reset(self):
        self.calls = 0
        self._closes = {}
        return None

    def adapt(self, intervention: Any) -> None:
        """Accept validated context entries for future repair delivery.

        Mirrors the E4 benchmark adapt() surface so admitted
        LearnedContext packages remain deliverable; entries are stored,
        never executed as instructions.
        """
        entries = []
        if isinstance(intervention, Mapping):
            entries = intervention.get("entries", []) or []
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            if not entry.get("context_id"):
                continue
            if not entry.get("failure_mechanism"):
                continue
            if not entry.get("corrective_principle"):
                continue
            self.learned_contexts.append(dict(entry))
        return None

    # -- observation memory -------------------------------------------

    def _remember(self, payload: Mapping[str, Any]) -> None:
        ts = payload.get("decision_timestamp")
        for name in INSTRUMENTS:
            close = _slot_close(payload, f"{NSE_ASSET_ID}:{name}")
            if close is None or not isinstance(ts, str):
                continue
            buf = self._closes.setdefault(name, [])
            if buf and buf[-1][0] == ts:
                continue
            buf.append((ts, close))

    def _trend(self, name: str) -> Optional[float]:
        lookback = int(self.params["trend_lookback"])
        buf = self._closes.get(name, [])
        if len(buf) <= lookback:
            return None
        old = buf[-1 - lookback][1]
        new = buf[-1][1]
        if old == 0:
            return None
        return (new - old) / old

    # -- policy --------------------------------------------------------

    def act(self, observation: Any) -> List[Dict[str, Any]]:
        payload = as_dict(observation)
        self.calls += 1
        self._remember(payload)
        vix = read_indicator_close(payload, VIX_SLOT)
        if vix is None:
            return []
        cash = read_cash(payload)
        if cash is None:
            return []
        positions = read_positions(payload)
        if vix > self.params["vix_high"]:
            return self._reduce_all(positions)[
                :int(self.params["max_orders_per_session"])]
        if vix >= self.params["vix_low"]:
            return []  # MID regime: maintain, never initiate (F-VOL guard)
        return self._accumulate(payload, cash, positions)[
            :int(self.params["max_orders_per_session"])]

    def _reduce_all(self, positions: Mapping[str, float]
                    ) -> List[Dict[str, Any]]:
        orders = []
        for name in INSTRUMENTS:
            held = positions.get(position_key(NSE_ASSET_ID, name), 0.0)
            if held > 0:
                orders.append(build_order(
                    NSE_ASSET_ID, name, "SELL",
                    min(held, float(self.params["sell_q"]))))
        return orders

    def _size_qty(self, held: float, close: float, cash: float) -> int:
        """Entry/add sizing. fixed_cash (F0): full tier iff cash covers
        CASH_FULL. affordability (F0R): full 2-lot entries only when
        affordable at price (capital-scaled, varies by name/session);
        adds to held names always taper to 1 (pyramiding)."""
        if self.params["sizing_mode"] == "affordability":
            if held > 0:
                return int(self.params["buy_q_small"])
            full = int(self.params["buy_q_full"])
            if full * close * (1.0 + TXN_RATE) + float(
                    self.params["cash_dust"]) <= cash:
                return full
            return int(self.params["buy_q_small"])
        if cash >= float(self.params["cash_full"]):
            return int(self.params["buy_q_full"])
        return int(self.params["buy_q_small"])

    def _accumulate(self, payload: Mapping[str, Any], cash: float,
                    positions: Mapping[str, float]) -> List[Dict[str, Any]]:
        orders: List[Dict[str, Any]] = []
        names_held = sum(
            1 for n in INSTRUMENTS
            if positions.get(position_key(NSE_ASSET_ID, n), 0.0) > 0)
        for name in INSTRUMENTS:
            held = positions.get(position_key(NSE_ASSET_ID, name), 0.0)
            trend = self._trend(name)
            if held > 0 and trend is not None and trend < float(
                    self.params["trend_sell"]):
                orders.append(build_order(
                    NSE_ASSET_ID, name, "SELL",
                    min(held, float(self.params["sell_q"]))))
                continue
            if trend is None or trend <= float(self.params["trend_min"]):
                continue  # unknown or weak trend: no initiation
            if names_held >= int(self.params["max_names_held"]):
                continue
            close = _slot_close(payload, f"{NSE_ASSET_ID}:{name}")
            if close is None:
                continue
            if held * close >= float(self.params["max_name_cost"]):
                continue
            if cash < float(self.params["cash_dust"]):
                continue
            qty = self._size_qty(held, close, cash)
            orders.append(build_order(NSE_ASSET_ID, name, "BUY", qty))
            names_held += 1 if held == 0 else 0
        return orders
