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

# v1.1 ladder/exit/pause constants (F3-frozen with rationale in
# configs/choice_agent/f3.yaml; inert under policy_version "1.0").
# A. sizing ladder (FinRL risk-scaling pattern: size falls as exposure
#    and concentration rise; round tiers, not fitted cut-points).
EXP_TIER_FULL = 0.25
EXP_TIER_HALT = 0.5
CONC_CAP = 0.4
# B. staged exits (standard drawdown-control pattern: trim then flatten;
#    creates exits outside the HIGH-VIX liquidation regime).
DD_TRIM = -0.05
DD_FLATTEN = -0.10
# C. cash-trajectory pause (treasury-preservation pattern: pause adds
#    after sharp cash depletion; exits unaffected).
CASH_DROP = 0.20
CASH_WINDOW = 5

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

# v1.1 additive parameters (absent = v1.0 behaviour, byte-identical).
V11_DEFAULTS = {
    "exp_tier_full": EXP_TIER_FULL,
    "exp_tier_halt": EXP_TIER_HALT,
    "conc_cap": CONC_CAP,
    "dd_trim": DD_TRIM,
    "dd_flatten": DD_FLATTEN,
    "cash_drop": CASH_DROP,
    "cash_window": CASH_WINDOW,
}


def _slot_close(payload: Mapping[str, Any], slot_key: str
                ) -> Optional[float]:
    """Read one equity/indicator close via the shared AVAILABLE-checked
    reader (None on missing/unavailable — never imputed)."""
    return read_indicator_close(payload, slot_key)


def _pfolio_number(payload: Mapping[str, Any], key: str
                 ) -> Optional[float]:
    """Agent-side finite reader for portfolio snapshot fields.

    Mirrors benchmarks/observation.py semantics (finite or None, never
    imputed) without touching the frozen module.
    """
    portfolio = payload.get("portfolio", {})
    if not isinstance(portfolio, Mapping):
        return None
    value = portfolio.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


class ChoiceAccumulator:
    """Deterministic regime-gated accumulator with exits."""

    identity = AgentIdentity(AGENT_ID, AGENT_VERSION)

    def __init__(self, config: Mapping[str, Any] | None = None,
                 policy_version: str = "1.0"):
        """Optional overrides (F0-repeat); defaults are the frozen F0
        constants above. Effective constants are fingerprinted into
        every experiment manifest; F0 traces remain reproducible via
        defaults."""
        if policy_version not in ("1.0", "1.1"):
            raise ValueError(f"unknown policy_version: {policy_version!r}")
        self.policy_version = policy_version
        if policy_version == "1.1":
            self.identity = AgentIdentity(AGENT_ID, "1.1")
        cfg = dict(config or {})
        unknown = set(cfg) - set(DEFAULTS) - set(V11_DEFAULTS)
        if unknown:
            raise ValueError(f"unknown policy keys: {sorted(unknown)}")
        self.params = {**DEFAULTS, **V11_DEFAULTS, **cfg}
        self.calls = 0
        self.learned_contexts: List[Any] = []
        # Own-observation history: {slot_key: [(timestamp, close)]}.
        self._closes: Dict[str, List[Any]] = {}
        # Own portfolio history: [(timestamp, cash, total_equity)].
        self._pfhist: List[Any] = []

    def reset(self):
        self.calls = 0
        self._closes = {}
        self._pfhist = []
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
        if isinstance(ts, str):
            cash = _pfolio_number(payload, "cash")
            equity = _pfolio_number(payload, "total_equity")
            if cash is not None and equity is not None:
                if not self._pfhist or self._pfhist[-1][0] != ts:
                    self._pfhist.append((ts, cash, equity))

    def _drawdown(self) -> Optional[float]:
        """Own-observed equity drawdown vs trailing peak (v1.1 staged
        exits). None until two observations exist."""
        eqs = [e for _, _, e in self._pfhist]
        if len(eqs) < 2:
            return None
        peak = max(eqs)
        if peak <= 0:
            return None
        return (eqs[-1] - peak) / peak

    def _cash_depleted(self) -> bool:
        """True when cash fell > CASH_DROP over the trailing CASH_WINDOW
        own-observations (v1.1 participation pause)."""
        window = int(self.params["cash_window"])
        cashes = [c for _, c, _ in self._pfhist[-window:]]
        if len(cashes) < window or cashes[0] <= 0:
            return False
        return (cashes[-1] - cashes[0]) / cashes[0] < -float(
            self.params["cash_drop"])

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
        if self.policy_version == "1.1":
            dd = self._drawdown()
            if dd is not None and dd < float(self.params["dd_flatten"]):
                return self._flatten(positions)[
                    :int(self.params["max_orders_per_session"])]
            if dd is not None and dd < float(self.params["dd_trim"]):
                return self._trim(positions)[
                    :int(self.params["max_orders_per_session"])]
        if vix > self.params["vix_high"]:
            return self._reduce_all(positions)[
                :int(self.params["max_orders_per_session"])]
        if vix >= self.params["vix_low"]:
            return []  # MID regime: maintain, never initiate (F-VOL guard)
        if self.policy_version == "1.1" and self._cash_depleted():
            return []  # C. treasury pause: depleted cash, no new BUYs
        return self._accumulate(payload, cash, positions)[
            :int(self.params["max_orders_per_session"])]

    def _flatten(self, positions: Mapping[str, float]
                 ) -> List[Dict[str, Any]]:
        """v1.1 staged exit, deep tier: SELL entire held quantity."""
        orders = []
        for name in INSTRUMENTS:
            held = positions.get(position_key(NSE_ASSET_ID, name), 0.0)
            if held > 0:
                orders.append(build_order(NSE_ASSET_ID, name, "SELL", held))
        return orders

    def _trim(self, positions: Mapping[str, float]
              ) -> List[Dict[str, Any]]:
        """v1.1 staged exit, shallow tier: trim one lot per held name."""
        orders = []
        for name in INSTRUMENTS:
            held = positions.get(position_key(NSE_ASSET_ID, name), 0.0)
            if held > 0:
                orders.append(build_order(NSE_ASSET_ID, name, "SELL",
                                          min(held, 1.0)))
        return orders

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
        v11 = self.policy_version == "1.1"
        exposure = _pfolio_number(payload, "exposure")
        equity = _pfolio_number(payload, "total_equity")
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
            if v11:
                # A. sizing ladder: exposure brake + concentration taper.
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
