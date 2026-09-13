"""Research-safe action interface: tradable assets only.

Actions are position deltas (orders), each naming an explicit instrument:

    {"asset_id": "nse_equity", "instrument": "RELIANCE:EQ",
     "side": "BUY", "quantity": 10.0}

Validation is deterministic and reason-coded. Orders naming CPI, IIP,
policy rates, G-Sec/T-bills, Brent, VIX, NIFTY, USD/INR, or any unknown
asset are rejected as NOOP_NON_TRADEABLE_ASSET / NOOP_UNKNOWN_ASSET: the
action interface can never trade information assets. Status vocabulary
reuses environment.portfolio.accounting codes; calendar/price gates add
explicit session codes below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from environment.portfolio.accounting import (
    STATUS_EXECUTED_FULL,
    STATUS_EXECUTED_PARTIAL,
    STATUS_NOOP_HOLD,
    STATUS_NOOP_INVALID_ACTION,
    STATUS_NOOP_INVALID_QUANTITY,
    STATUS_NOOP_NON_POSITIVE_QUANTITY,
    STATUS_NOOP_NO_CASH,
    STATUS_NOOP_NO_POSITION,
    BINDING_CASH,
    BINDING_POSITION,
)
from environment.indian.registry import ASSET_REGISTRY, get_spec

# Additional session/price gate codes for the multi-asset environment.
STATUS_NOOP_UNKNOWN_ASSET = "NOOP_UNKNOWN_ASSET"
STATUS_NOOP_NON_TRADEABLE_ASSET = "NOOP_NON_TRADEABLE_ASSET"
STATUS_NOOP_UNKNOWN_INSTRUMENT = "NOOP_UNKNOWN_INSTRUMENT"
STATUS_NOOP_NO_PRICE = "NOOP_NO_PRICE"
STATUS_NOOP_MARKET_CLOSED = "NOOP_MARKET_CLOSED"
STATUS_NOOP_UNKNOWN_CALENDAR = "NOOP_UNKNOWN_CALENDAR"

VALID_SIDES = ("BUY", "SELL")

# Tradable asset_ids. Single source of truth derived from the registry:
# role == TRADEABLE. Anything else is rejected, no exceptions.
TRADEABLE_ASSETS = tuple(
    spec.asset_id for spec in ASSET_REGISTRY.values() if spec.tradable
)


@dataclass
class ValidatedOrder:
    asset_id: str
    instrument: str
    side: str  # BUY | SELL | HOLD | INVALID
    requested_quantity: float
    status: str  # pre-execution validation outcome; OK == "VALIDATED"
    constraint_binding: Optional[str] = None
    detail: str = ""


@dataclass
class OrderResult:
    asset_id: str
    instrument: str
    action_normalized: str
    requested_quantity: float
    executed_quantity: float
    execution_price: float
    transaction_cost: float
    status: str
    constraint_binding: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "instrument": self.instrument,
            "action_normalized": self.action_normalized,
            "requested_quantity": self.requested_quantity,
            "executed_quantity": self.executed_quantity,
            "execution_price": self.execution_price,
            "transaction_cost": self.transaction_cost,
            "execution_status": self.status,
            "constraint_binding": self.constraint_binding,
        }


def _as_quantity(quantity: Any) -> Optional[float]:
    if isinstance(quantity, bool) or not isinstance(quantity, (int, float)):
        return None
    return float(quantity)


def validate_orders(orders: Any) -> List[ValidatedOrder]:
    """Deterministically validate a submitted order list.

    Never raises on malformed input: every order yields exactly one
    ValidatedOrder with a reason code. Non-list submissions yield [].
    """
    if not isinstance(orders, list):
        return []
    out: List[ValidatedOrder] = []
    for raw in orders:
        if not isinstance(raw, dict):
            out.append(ValidatedOrder("", "", "INVALID", 0.0,
                                      STATUS_NOOP_INVALID_ACTION,
                                      detail="Order must be a mapping."))
            continue
        asset_id = raw.get("asset_id")
        instrument = raw.get("instrument", "")
        side = raw.get("side", "HOLD")
        side = side.upper() if isinstance(side, str) else "INVALID"
        qty = _as_quantity(raw.get("quantity", 0.0))
        if asset_id not in ASSET_REGISTRY:
            out.append(ValidatedOrder(str(asset_id), str(instrument), "INVALID",
                                      qty or 0.0, STATUS_NOOP_UNKNOWN_ASSET,
                                      detail=f"Unknown asset_id {asset_id!r}."))
            continue
        if asset_id not in TRADEABLE_ASSETS:
            out.append(ValidatedOrder(asset_id, str(instrument), "INVALID",
                                      qty or 0.0, STATUS_NOOP_NON_TRADEABLE_ASSET,
                                      detail=f"Asset {asset_id!r} is not tradable."))
            continue
        if not isinstance(instrument, str) or not instrument:
            out.append(ValidatedOrder(asset_id, "", "INVALID",
                                      qty or 0.0, STATUS_NOOP_UNKNOWN_INSTRUMENT,
                                      detail="Instrument must be a non-empty string."))
            continue
        if asset_id == "nse_equity" and ":" not in instrument:
            out.append(ValidatedOrder(asset_id, str(instrument), "INVALID",
                                      qty or 0.0, STATUS_NOOP_UNKNOWN_INSTRUMENT,
                                      detail="Equity instrument must be 'SYMBOL:SERIES'."))
            continue
        if side not in VALID_SIDES:
            out.append(ValidatedOrder(asset_id, str(instrument),
                                      side if side in ("HOLD",) else "INVALID",
                                      qty or 0.0,
                                      STATUS_NOOP_HOLD if side == "HOLD"
                                      else STATUS_NOOP_INVALID_ACTION))
            continue
        if qty is None:
            out.append(ValidatedOrder(asset_id, str(instrument), side, 0.0,
                                      STATUS_NOOP_INVALID_QUANTITY))
            continue
        if qty <= 0:
            out.append(ValidatedOrder(asset_id, str(instrument), side, qty,
                                      STATUS_NOOP_NON_POSITIVE_QUANTITY))
            continue
        out.append(ValidatedOrder(asset_id, str(instrument), side, qty, "VALIDATED"))
    return out
