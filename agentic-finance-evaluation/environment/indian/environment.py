"""Multi-asset Indian research environment.

Clock: master grid of NSE_CM OPEN/SPECIAL sessions. At decision date t the
agent sees market bars strictly before t (observation-lag path) plus macro
vintages with availability <= t (InformationSet path). Valid orders
submitted at t execute at t's session close; orders are NOT implicitly
carried forward. Unknown/closed sessions or missing bars reject the order
with an explicit NOOP code. Same-bar closes never enter the decision
state, so future prices cannot influence actions, rewards, or validation.

Reward is portfolio-value change inclusive of transaction costs only. No
risk-adjusted scoring lives here; that belongs in evaluation.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Dict, List, Optional

from environment.indian.actions import (
    STATUS_NOOP_HOLD,
    OrderResult,
    validate_orders,
)
from environment.indian.asset_contract import ROLE_INFORMATION
from environment.indian.clock import build_master_grid, load_default_resolver
from environment.indian.information_lookup import (
    STATUS_AVAILABLE,
    InformationLookup,
)
from environment.indian.portfolio import MultiAssetPortfolio, _instrument_key
from environment.indian.registry import get_spec
from environment.indian.state import EnvironmentState, PortfolioView

STATUS_NOOP_EPISODE_DONE = "NOOP_EPISODE_DONE"

# Assets exposed in the macro block of every state.
MACRO_ASSETS = ("gsec10y", "tbill91d", "tbill364d", "rbi_policy", "cpi", "iip", "brent")


class IndianMultiAssetEnvironment:
    def __init__(self, config: Dict[str, Any], base_dir: str = "."):
        self.config = dict(config)
        self.base_dir = base_dir
        self.strict = bool(config.get("strict_pit", True))
        self.vintage_policy = config.get("vintage_policy", "explicit")
        self.costs_bps = float(config.get("transaction_cost_bps", 5.0))
        self.initial_cash = float(config.get("initial_cash", 100000.0))
        uni = config.get("universe", {})
        self.equity_universe: List[str] = list(uni.get("nse_equity", []))
        self.gold_universe: List[str] = list(uni.get("mcx_gold", []))
        if not self.equity_universe and not self.gold_universe:
            raise ValueError("universe must name at least one tradable instrument")
        for inst in self.equity_universe:
            _equity_filter(inst)  # fail fast on malformed config
        for inst in self.gold_universe:
            if not inst:
                raise ValueError("gold universe instruments must be non-empty")
        # Configured tradable universe: the experiment's source of truth.
        # Never inferred from the dataset, never expanded automatically.
        self.allowed_instruments = {
            "nse_equity": set(self.equity_universe),
            "mcx_gold": set(self.gold_universe),
        }
        self.lookup = InformationLookup(base_dir=base_dir, strict=self.strict)
        self.resolver = load_default_resolver(base_dir)
        self.grid = build_master_grid(
            self.resolver,
            _as_date(config.get("start_date")),
            _as_date(config.get("end_date")),
        )
        self.portfolio = MultiAssetPortfolio(self.initial_cash, self.costs_bps)
        self.peak_value = self.initial_cash
        self.index = 0
        self.done = False

    # -- introspection -------------------------------------------------

    def spec(self) -> Dict[str, Any]:
        return {
            "grid_start": self.grid[0].isoformat(),
            "grid_end": self.grid[-1].isoformat(),
            "grid_sessions": len(self.grid),
            "market_fingerprint": self.fingerprint(),
            "initial_cash": self.initial_cash,
            "transaction_cost_bps": self.costs_bps,
            "strict_pit": self.strict,
            "vintage_policy": self.vintage_policy,
            "equity_universe": list(self.equity_universe),
            "gold_universe": list(self.gold_universe),
        }

    def fingerprint(self) -> str:
        parts = [d.isoformat() for d in self.grid]
        for inst in sorted(self.equity_universe):
            f = _equity_filter(inst)
            closes = ",".join(
                repr(self.lookup.bar_close("nse_equity", f, d.isoformat()))
                for d in self.grid)
            parts.append(f"{inst}:{closes}")
        for inst in sorted(self.gold_universe):
            closes = ",".join(
                repr(self.lookup.bar_close(
                    "mcx_gold", {"contract_symbol": inst}, d.isoformat()))
                for d in self.grid)
            parts.append(f"{inst}:{closes}")
        parts.append(repr(self.costs_bps))
        return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()

    # -- episodes ------------------------------------------------------

    def reset(self) -> Dict[str, Any]:
        self.portfolio = MultiAssetPortfolio(self.initial_cash, self.costs_bps)
        self.peak_value = self.initial_cash
        self.index = 0
        self.done = False
        return self._state_at(self.grid[0]).to_dict()

    def step(self, orders: Any) -> tuple:
        """Submit an order list; returns (state, info, done, meta)."""
        if self.done:
            state = self._state_at(self.grid[self.index])
            equity = state.portfolio.total_equity
            return state.to_dict(), {
                "step_pnl": 0.0,
                "cumulative_pnl": equity - self.initial_cash,
                "drawdown": _drawdown(self.peak_value, equity),
                "transaction_costs": 0.0,
                "executions": [],
                "portfolio_value": equity,
                "cash": state.portfolio.cash,
                "positions": state.portfolio.positions,
                "date": state.decision_timestamp,
                "action_normalized": "HOLD",
                "requested_quantity": 0.0,
                "executed_quantity": 0.0,
                "execution_status": STATUS_NOOP_EPISODE_DONE,
                "constraint_binding": None,
            }, True, {"reason": "episode_already_done"}

        today = self.grid[self.index]
        pre_state = self._state_at(today)
        pre_equity = pre_state.portfolio.total_equity

        validated = validate_orders(orders, self.allowed_instruments)
        validated.sort(key=lambda o: (o.asset_id, o.instrument))
        results: List[OrderResult] = []
        fees = 0.0
        for order in validated:
            if order.status != "VALIDATED":
                results.append(OrderResult(
                    order.asset_id, order.instrument, order.side,
                    order.requested_quantity, 0.0, 0.0, 0.0,
                    order.status, order.constraint_binding))
                continue
            venue = get_spec(order.asset_id).venue
            res = self.resolver.resolve(venue, today)
            if res.market_status == "UNKNOWN":
                session_open = None
            else:
                session_open = res.market_status in ("OPEN", "SPECIAL")
            price = self._execution_price(order.asset_id, order.instrument, today)
            out = self.portfolio.execute_validated(order, price, session_open)
            fees += out.transaction_cost
            results.append(out)

        if self.index >= len(self.grid) - 1:
            self.done = True
            equity = self.portfolio.mark(
                self._marks_for(self.portfolio.snapshot(), today))["total_equity"]
            self.peak_value = max(self.peak_value, equity)
            info = self._info(today.isoformat(), pre_equity, equity, fees,
                              results, "market_exhausted")
            return self._state_at(today, force_marks_today=True).to_dict(), info, True, {
                "reason": "market_exhausted"}

        self.index += 1
        next_state = self._state_at(self.grid[self.index])
        equity = next_state.portfolio.total_equity
        self.peak_value = max(self.peak_value, equity)
        info = self._info(self.grid[self.index].isoformat(), pre_equity,
                          equity, fees, results, None)
        return next_state.to_dict(), info, False, {}

    # -- internals -----------------------------------------------------

    def _execution_price(self, asset_id: str, instrument: str, day: date) -> Optional[float]:
        iso = day.isoformat()
        if asset_id == "nse_equity":
            return self.lookup.bar_close("nse_equity", _equity_filter(instrument), iso)
        if asset_id == "mcx_gold":
            return self.lookup.bar_close(
                "mcx_gold", {"contract_symbol": instrument}, iso)
        return None

    def _marks_for(self, positions: Dict[str, Dict[str, float]],
                   day: date) -> Dict[str, float]:
        iso = day.isoformat()
        marks: Dict[str, float] = {}
        for key in positions:
            asset_id, _, instrument = key.partition(":")
            price = self._execution_price(asset_id, instrument, day)
            if price is not None:
                marks[key] = price
        return marks

    def _state_at(self, day: date, force_marks_today: bool = False) -> EnvironmentState:
        stamp = day.isoformat()
        market: Dict[str, Any] = {}
        for inst in self.equity_universe:
            slot = self.lookup.get_information(
                "nse_equity", stamp, self.vintage_policy, _equity_filter(inst))
            market[f"nse_equity:{inst}"] = slot
        for inst in self.gold_universe:
            slot = self.lookup.get_information(
                "mcx_gold", stamp, self.vintage_policy, {"contract_symbol": inst})
            market[f"mcx_gold:{inst}"] = slot
        for aid in ("nifty50", "indiavix", "usd_inr"):
            market[aid] = self.lookup.get_information(aid, stamp, self.vintage_policy)
        macro = {}
        for aid in MACRO_ASSETS:
            macro[aid] = self.lookup.get_information(aid, stamp, self.vintage_policy)
        # Marks use bars visible at this state (prior closes), except the
        # terminal state which marks at today's execution closes.
        if force_marks_today:
            marks = self._marks_for(self.portfolio.snapshot(), day)
        else:
            marks = {}
            for key in self.portfolio.snapshot():
                asset_id, _, instrument = key.partition(":")
                filt = (_equity_filter(instrument) if asset_id == "nse_equity"
                        else {"contract_symbol": instrument})
                slot = self.lookup.get_information(asset_id, stamp,
                                                   self.vintage_policy, filt)
                vals = slot.values
                price = vals.get("close", vals.get("settlement_price",
                                 vals.get("rate", vals.get("yield_pct"))))
                if price is not None:
                    marks[key] = float(price)
        valuation = self.portfolio.mark(marks)
        portfolio = PortfolioView(
            cash=self.portfolio.cash,
            positions={k: dict(v) for k, v in self.portfolio.snapshot().items()},
            holdings_value=valuation["holdings_value"],
            total_equity=valuation["total_equity"],
            exposure=valuation["exposure"],
            realized_pnl=self.portfolio.realized_pnl,
            unrealized_pnl=valuation["unrealized_pnl"],
            cumulative_costs=self.portfolio.cumulative_transaction_costs,
        )
        calendar = {
            "NSE_CM": self.resolver.resolve("NSE_CM", day).market_status,
            "MCX": self.resolver.resolve("MCX", day).market_status,
        }
        return EnvironmentState(decision_timestamp=stamp, market=market,
                                macro=macro, portfolio=portfolio, calendar=calendar)

    def _info(self, stamp, pre_equity, equity, fees, results, terminal_reason):
        return {
            "step_pnl": equity - pre_equity,
            "cumulative_pnl": equity - self.initial_cash,
            "drawdown": _drawdown(self.peak_value, equity),
            "transaction_costs": fees,
            "executions": [r.to_dict() for r in results],
            "execution_price": results[0].execution_price if results else 0.0,
            "portfolio_value": equity,
            "cash": self.portfolio.cash,
            "positions": self.snapshot_positions(),
            "date": stamp,
            "action_normalized": results[0].action_normalized if len(results) == 1 else "BASKET",
            "requested_quantity": sum(r.requested_quantity for r in results),
            "executed_quantity": sum(r.executed_quantity for r in results),
            "execution_status": results[0].status if len(results) == 1 else "BASKET",
            "constraint_binding": results[0].constraint_binding if len(results) == 1 else None,
        }

    def snapshot_positions(self):
        return {k: dict(v) for k, v in self.portfolio.snapshot().items()}


def _drawdown(peak: float, equity: float) -> float:
    return (peak - equity) / peak if peak > 0 else 0.0


def _as_date(value: Any) -> date:
    import pandas as pd
    day = pd.to_datetime(value, errors="raise").date()
    if not isinstance(day, date):
        raise ValueError(f"invalid grid bound {value!r}")
    return day


def _equity_filter(instrument: str) -> Dict[str, str]:
    symbol, _, series = instrument.partition(":")
    if not symbol or not series:
        raise ValueError(
            f"equity instrument must be 'SYMBOL:SERIES', got {instrument!r}")
    return {"symbol": symbol, "series": series}
