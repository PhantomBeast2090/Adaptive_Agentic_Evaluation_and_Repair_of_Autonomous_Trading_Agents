"""Portfolio accounting for the single-asset Phase 1.5 replay environment.

Execution economics (fill sizes, fees, cash/position clipping) are unchanged
from the frozen Phase 1.5 contract. Phase 2 adds an explicit `ExecutionReport`
so that constraint-compliance and safety dimensions can be measured from
recorded evidence rather than re-derived by guesswork from portfolio deltas.
"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

VALID_ACTIONS = ("BUY", "SELL", "HOLD")

# Execution status codes. Exactly one is assigned per submitted action.
STATUS_EXECUTED_FULL = "EXECUTED_FULL"
STATUS_EXECUTED_PARTIAL = "EXECUTED_PARTIAL"
STATUS_NOOP_HOLD = "NOOP_HOLD"
STATUS_NOOP_INVALID_ACTION = "NOOP_INVALID_ACTION"
STATUS_NOOP_INVALID_QUANTITY = "NOOP_INVALID_QUANTITY"
STATUS_NOOP_NON_POSITIVE_QUANTITY = "NOOP_NON_POSITIVE_QUANTITY"
STATUS_NOOP_NON_POSITIVE_PRICE = "NOOP_NON_POSITIVE_PRICE"
STATUS_NOOP_NO_CASH = "NOOP_NO_CASH"
STATUS_NOOP_NO_POSITION = "NOOP_NO_POSITION"

# Which environment constraint stopped the order from filling as requested.
BINDING_CASH = "cash"
BINDING_POSITION = "position"


@dataclass(frozen=True)
class ExecutionReport:
    """Observable record of what the environment did with one submitted action.

    `requested_quantity` is what the agent asked for; `executed_quantity` is
    what the environment filled. The gap between them, together with
    `constraint_binding`, is the evidence used by the constraint and safety
    evaluators.
    """

    action_normalized: str
    requested_quantity: float
    executed_quantity: float
    execution_price: float
    transaction_cost: float
    status: str
    constraint_binding: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _as_report_quantity(quantity: Any) -> Optional[float]:
    """Coerce a submitted quantity for reporting only. None means non-numeric."""
    if isinstance(quantity, bool) or not isinstance(quantity, (int, float)):
        return None
    return float(quantity)


class Portfolio:
    def __init__(self, initial_cash: float, transaction_cost_bps: float = 5.0):
        if initial_cash < 0:
            raise ValueError("initial_cash must be non-negative")
        if transaction_cost_bps < 0:
            raise ValueError("transaction_cost_bps must be non-negative")

        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.holdings = 0.0  # Number of shares
        self.transaction_cost_bps = transaction_cost_bps
        self.cumulative_transaction_costs = 0.0

    def get_value(self, current_price: float) -> float:
        if current_price < 0:
            raise ValueError("current_price must be non-negative")
        return self.cash + (self.holdings * current_price)

    def execute_trade(self, action: str, quantity: float, price: float) -> float:
        """Execute an action and return the transaction cost charged.

        Retained for callers that only need the fee. `execute` is the primary
        entry point and returns the full observable execution record.
        """
        return self.execute(action, quantity, price).transaction_cost

    def execute(self, action: Any, quantity: Any, price: float) -> ExecutionReport:
        """Execute an action and return an observable ExecutionReport.

        Fill and fee arithmetic is identical to the Phase 1.5 contract:
        oversized buys are clipped to the maximum affordable quantity, oversized
        sells are clipped to available holdings, and every other malformed
        submission is a no-op.
        """
        normalized = action.upper() if isinstance(action, str) else None
        requested = _as_report_quantity(quantity)

        def noop(status: str, binding: Optional[str] = None) -> ExecutionReport:
            return ExecutionReport(
                action_normalized=normalized if normalized in VALID_ACTIONS else "INVALID",
                requested_quantity=requested if requested is not None else 0.0,
                executed_quantity=0.0,
                execution_price=float(price),
                transaction_cost=0.0,
                status=status,
                constraint_binding=binding,
            )

        if normalized not in VALID_ACTIONS:
            return noop(STATUS_NOOP_INVALID_ACTION)
        if normalized == "HOLD":
            return noop(STATUS_NOOP_HOLD)
        if requested is None:
            return noop(STATUS_NOOP_INVALID_QUANTITY)
        if price <= 0:
            return noop(STATUS_NOOP_NON_POSITIVE_PRICE)
        if requested <= 0:
            return noop(STATUS_NOOP_NON_POSITIVE_QUANTITY)

        cost_rate = self.transaction_cost_bps / 10000.0

        if normalized == "BUY":
            cost = requested * price
            tx_fee = cost * cost_rate
            if self.cash >= (cost + tx_fee):
                self.cash -= cost + tx_fee
                self.holdings += requested
                self.cumulative_transaction_costs += tx_fee
                return ExecutionReport(
                    action_normalized="BUY",
                    requested_quantity=requested,
                    executed_quantity=requested,
                    execution_price=float(price),
                    transaction_cost=tx_fee,
                    status=STATUS_EXECUTED_FULL,
                )

            # Insufficient cash: fill the maximum affordable quantity.
            max_qty = (self.cash / (1 + cost_rate)) / price
            if max_qty <= 0:
                return noop(STATUS_NOOP_NO_CASH, BINDING_CASH)

            tx_fee = (max_qty * price) * cost_rate
            self.cash -= max_qty * price + tx_fee
            self.holdings += max_qty
            self.cumulative_transaction_costs += tx_fee
            return ExecutionReport(
                action_normalized="BUY",
                requested_quantity=requested,
                executed_quantity=max_qty,
                execution_price=float(price),
                transaction_cost=tx_fee,
                status=STATUS_EXECUTED_PARTIAL,
                constraint_binding=BINDING_CASH,
            )

        # SELL
        qty_to_sell = min(requested, self.holdings)
        if qty_to_sell <= 0:
            return noop(STATUS_NOOP_NO_POSITION, BINDING_POSITION)

        revenue = qty_to_sell * price
        tx_fee = revenue * cost_rate
        self.cash += revenue - tx_fee
        self.holdings -= qty_to_sell
        self.cumulative_transaction_costs += tx_fee
        filled_fully = qty_to_sell >= requested
        return ExecutionReport(
            action_normalized="SELL",
            requested_quantity=requested,
            executed_quantity=qty_to_sell,
            execution_price=float(price),
            transaction_cost=tx_fee,
            status=STATUS_EXECUTED_FULL if filled_fully else STATUS_EXECUTED_PARTIAL,
            constraint_binding=None if filled_fully else BINDING_POSITION,
        )
