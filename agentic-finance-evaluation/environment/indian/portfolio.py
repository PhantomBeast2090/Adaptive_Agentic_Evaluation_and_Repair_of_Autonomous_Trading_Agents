"""Deterministic multi-asset portfolio ledger.

Cash + per-instrument positions with average-cost accounting. Fill and fee
arithmetic mirrors the frozen single-asset contract per order (clip buys to
affordable quantity, clip sells to holdings, malformed -> no-op), applied
sequentially in sorted (asset_id, instrument) order so multi-order fills
are reproducible. No short selling, no leverage: total order cost can never
exceed cash, and sells can never exceed holdings.

Missing execution price (NaN/gap/closed session) rejects the order with an
explicit reason; future prices are never substituted.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from environment.indian.actions import (
    BINDING_CASH,
    BINDING_POSITION,
    STATUS_EXECUTED_FULL,
    STATUS_EXECUTED_PARTIAL,
    STATUS_NOOP_HOLD,
    STATUS_NOOP_INVALID_ACTION,
    STATUS_NOOP_INVALID_QUANTITY,
    STATUS_NOOP_MARKET_CLOSED,
    STATUS_NOOP_NON_POSITIVE_QUANTITY,
    STATUS_NOOP_NO_CASH,
    STATUS_NOOP_NO_POSITION,
    STATUS_NOOP_NO_PRICE,
    STATUS_NOOP_UNKNOWN_CALENDAR,
    STATUS_NOOP_UNKNOWN_INSTRUMENT,
    OrderResult,
    ValidatedOrder,
)


class MultiAssetPortfolio:
    def __init__(self, initial_cash: float, transaction_cost_bps: float = 5.0):
        if initial_cash < 0:
            raise ValueError("initial_cash must be non-negative")
        if transaction_cost_bps < 0:
            raise ValueError("transaction_cost_bps must be non-negative")
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.transaction_cost_bps = float(transaction_cost_bps)
        # instrument key -> {"quantity": float, "avg_cost": float}
        self.positions: Dict[str, Dict[str, float]] = {}
        self.realized_pnl = 0.0
        self.cumulative_transaction_costs = 0.0

    # -- valuation -----------------------------------------------------

    def mark(self, prices: Dict[str, float]) -> Dict[str, Any]:
        """Value holdings at explicit mark prices. Missing marks contribute 0
        to holdings value and are reported, never forward-filled."""
        holdings_value = 0.0
        unpriced: List[str] = []
        for key, pos in self.positions.items():
            price = prices.get(key)
            if price is None or not (price == price) or price < 0:
                unpriced.append(key)
                continue
            holdings_value += pos["quantity"] * price
        total_equity = self.cash + holdings_value
        unrealized = sum(
            (prices[k] - p["avg_cost"]) * p["quantity"]
            for k, p in self.positions.items() if k in prices
            and prices[k] == prices[k] and prices[k] >= 0
        )
        exposure = holdings_value / total_equity if total_equity > 0 else 0.0
        return {
            "holdings_value": holdings_value,
            "total_equity": total_equity,
            "exposure": exposure,
            "unrealized_pnl": unrealized,
            "unpriced": unpriced,
        }

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        return {k: dict(v) for k, v in self.positions.items()}

    # -- execution -----------------------------------------------------

    def execute_validated(
        self,
        order: ValidatedOrder,
        execution_price: Optional[float],
        session_open: Optional[bool] = None,
    ) -> OrderResult:
        """Execute one validated order at an explicit execution price.

        execution_price=None (missing bar) -> NOOP_NO_PRICE. session_open
        False -> NOOP_MARKET_CLOSED; None (unknown calendar) ->
        NOOP_UNKNOWN_CALENDAR. Fail-closed in all three cases.
        """
        key = _instrument_key(order.asset_id, order.instrument)
        if order.status != "VALIDATED":
            return OrderResult(order.asset_id, key, order.side,
                               order.requested_quantity, 0.0,
                               execution_price or 0.0, 0.0, order.status,
                               order.constraint_binding)
        if session_open is None:
            return OrderResult(order.asset_id, key, order.side,
                               order.requested_quantity, 0.0, 0.0, 0.0,
                               STATUS_NOOP_UNKNOWN_CALENDAR)
        if session_open is False:
            return OrderResult(order.asset_id, key, order.side,
                               order.requested_quantity, 0.0, 0.0, 0.0,
                               STATUS_NOOP_MARKET_CLOSED)
        if (execution_price is None or execution_price != execution_price
                or execution_price <= 0):
            return OrderResult(order.asset_id, key, order.side,
                               order.requested_quantity, 0.0, 0.0, 0.0,
                               STATUS_NOOP_NO_PRICE)
        rate = self.transaction_cost_bps / 10000.0
        if order.side == "BUY":
            return self._buy(key, order, execution_price, rate)
        return self._sell(key, order, execution_price, rate)

    def _buy(self, key, order, price, rate) -> OrderResult:
        cost = order.requested_quantity * price
        fee = cost * rate
        if self.cash >= cost + fee:
            self._add(key, order.requested_quantity, price)
            self.cash -= cost + fee
            self.cumulative_transaction_costs += fee
            return OrderResult(order.asset_id, key, "BUY",
                               order.requested_quantity,
                               order.requested_quantity, price, fee,
                               STATUS_EXECUTED_FULL)
        max_qty = (self.cash / (1 + rate)) / price
        if max_qty <= 0:
            return OrderResult(order.asset_id, key, "BUY",
                               order.requested_quantity, 0.0, price, 0.0,
                               STATUS_NOOP_NO_CASH, BINDING_CASH)
        fee = max_qty * price * rate
        self._add(key, max_qty, price)
        self.cash -= max_qty * price + fee
        self.cumulative_transaction_costs += fee
        return OrderResult(order.asset_id, key, "BUY",
                           order.requested_quantity, max_qty, price, fee,
                           STATUS_EXECUTED_PARTIAL, BINDING_CASH)

    def _sell(self, key, order, price, rate) -> OrderResult:
        held = self.positions.get(key, {"quantity": 0.0})["quantity"]
        qty = min(order.requested_quantity, held)
        if qty <= 0:
            return OrderResult(order.asset_id, key, "SELL",
                               order.requested_quantity, 0.0, price, 0.0,
                               STATUS_NOOP_NO_POSITION, BINDING_POSITION)
        revenue = qty * price
        fee = revenue * rate
        avg = self.positions[key]["avg_cost"]
        self.realized_pnl += (price - avg) * qty - fee
        self.cash += revenue - fee
        self.cumulative_transaction_costs += fee
        remaining = held - qty
        if remaining <= 1e-12:
            self.positions.pop(key, None)
        else:
            self.positions[key]["quantity"] = remaining
        full = qty >= order.requested_quantity
        return OrderResult(
            order.asset_id, key, "SELL", order.requested_quantity, qty,
            price, fee, STATUS_EXECUTED_FULL if full else STATUS_EXECUTED_PARTIAL,
            None if full else BINDING_POSITION)

    def _add(self, key: str, qty: float, price: float) -> None:
        pos = self.positions.get(key)
        if pos is None:
            self.positions[key] = {"quantity": qty, "avg_cost": price}
        else:
            total = pos["quantity"] + qty
            pos["avg_cost"] = (pos["avg_cost"] * pos["quantity"] + price * qty) / total
            pos["quantity"] = total


def _instrument_key(asset_id: str, instrument: str) -> str:
    return f"{asset_id}:{instrument}"
