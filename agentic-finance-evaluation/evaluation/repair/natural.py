"""Natural Indian-market trajectory adapter for M-R6 (additive).

Converts canonical Indian-market DecisionRecords into the diagnostic
session representation consumed by the frozen M-R5 detectors, plus the
PIT-safe helpers the runner needs (trigger matching, compliance,
target metrics, paired statistics inputs).

FIELD PROVENANCE (every field documented; nothing retrospective):
  session            decision_timestamp (record identity, already known)
  buy_quantity       sum of submitted BUY quantities (agent's own orders)
  sell_quantity      sum of submitted SELL quantities (own orders)
  order_count        len(submitted_orders) (own orders)
  names_held         distinct instruments with qty>0 in portfolio_before
                     positions (pre-decision portfolio snapshot)
  exposure           portfolio_before.exposure (pre-decision snapshot)
  reward             record.reward (realised step outcome, used ONLY for
                     loss-episode grouping exactly as the frozen M-R5
                     detectors do; never a forward/MAE label)
  drawdown           peak-to-current decline of total_equity_before over
                     the already-observed prefix (no future data)
  unrealized_drawdown max(0, -unrealized_pnl/total_equity) from
                     portfolio_before (own-portfolio accounting; this is
                     what the wrapper's drawdown trigger field resolves)
  vix                India VIX close joined as-of-or-before the session
                     date (observation-lag join; never a future bar)
  cash               portfolio_before.cash (pre-decision snapshot)

FORBIDDEN (asserted absent by tests/test_mr6_natural.py):
  subsequent-session gains, adverse-excursion legs, post-decision
  prices, buy-and-hold counterfactuals, attribution outcomes, held-out
  P&L aggregates.
"""

from __future__ import annotations

import csv
import os
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

FORBIDDEN_SUBSTRINGS = (
    "forward_return",
    "mae",
    "mfe",
    "hold_return",
    "opportunity",
    "attribution",
)


def assert_no_forbidden_fields(record: Mapping[str, Any]) -> None:
    """Fail closed if a record carries retrospective outcome legs."""
    for key in ("forward_return_1d", "forward_return_3d", "mae", "mfe",
                "hold_return", "opportunity_return"):
        if key in record:
            raise ValueError(
                f"forbidden retrospective field {key!r} in diagnosis input")


def load_vix_map(base_dir: str) -> Dict[str, float]:
    """Date -> India VIX close from the canonical daily series."""
    path = os.path.join(
        base_dir, "data", "processed", "india", "market",
        "nse_india_vix_daily.csv")
    out: Dict[str, float] = {}
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                out[row["date"]] = float(row["close"])
            except (KeyError, TypeError, ValueError):
                continue
    return out


def vix_asof(vix_map: Mapping[str, float], date: str) -> Optional[float]:
    """Latest VIX close on or before the session date (lag join)."""
    best: Optional[str] = None
    for day in vix_map:
        if day <= date and (best is None or day > best):
            best = day
    return vix_map[best] if best is not None else None


def _positions_of(portfolio: Mapping[str, Any]) -> Dict[str, float]:
    positions = portfolio.get("positions", {})
    out: Dict[str, float] = {}
    if isinstance(positions, Mapping):
        for key, slot in positions.items():
            quantity = 0.0
            if isinstance(slot, Mapping):
                try:
                    quantity = float(slot.get("quantity", 0.0))
                except (TypeError, ValueError):
                    quantity = 0.0
            elif isinstance(slot, (int, float)) and not isinstance(
                    slot, bool):
                quantity = float(slot)
            if quantity > 0:
                out[str(key)] = quantity
    return out


def _finite(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def adapt_records(
    records: Sequence[Mapping[str, Any]],
    vix_map: Mapping[str, float],
) -> List[Dict[str, Any]]:
    """Adapt canonical DecisionRecords to diagnostic sessions.

    Accepts record mappings (or objects exposing ``to_dict()``).
    Raises on forbidden retrospective fields.
    """
    sessions: List[Dict[str, Any]] = []
    peak: Optional[float] = None
    for record in records:
        payload = (record.to_dict() if hasattr(record, "to_dict")
                   and callable(record.to_dict) else dict(record))
        for key in FORBIDDEN_SUBSTRINGS:
            for field in payload:
                if key in str(field).lower():
                    raise ValueError(
                        f"forbidden retrospective field {field!r} "
                        "in diagnosis input")
        timestamp = str(payload.get("decision_timestamp", ""))
        orders = payload.get("submitted_orders", []) or []
        buy_quantity = 0.0
        sell_quantity = 0.0
        for order in orders:
            if not isinstance(order, Mapping):
                continue
            try:
                quantity = float(order.get("quantity", 0.0))
            except (TypeError, ValueError):
                continue
            if quantity <= 0:
                continue
            if order.get("side") == "BUY":
                buy_quantity += quantity
            elif order.get("side") == "SELL":
                sell_quantity += quantity
        portfolio = payload.get("portfolio_before", {})
        if not isinstance(portfolio, Mapping):
            portfolio = {}
        positions = _positions_of(portfolio)
        equity = _finite(portfolio.get("total_equity"))
        cash = _finite(portfolio.get("cash"))
        exposure = _finite(portfolio.get("exposure"))
        unrealized = _finite(portfolio.get("unrealized_pnl"))
        if equity is not None:
            peak = equity if peak is None else max(peak, equity)
        drawdown = (max(0.0, (peak - equity) / peak)
                    if peak and equity is not None and peak > 0 else 0.0)
        unrealized_drawdown = (
            max(0.0, -unrealized / equity)
            if unrealized is not None and equity else 0.0)
        try:
            reward = float(payload.get("reward", 0.0))
            if reward != reward or reward in (float("inf"),
                                              float("-inf")):
                reward = 0.0
        except (TypeError, ValueError):
            reward = 0.0
        sessions.append({
            "session": timestamp,
            "buy_quantity": buy_quantity,
            "sell_quantity": sell_quantity,
            "order_count": sum(1 for o in orders
                               if isinstance(o, Mapping)),
            "names_held": len(positions),
            "exposure": exposure if exposure is not None else 0.0,
            "reward": reward,
            "drawdown": drawdown,
            "unrealized_drawdown": unrealized_drawdown,
            "vix": vix_asof(vix_map, timestamp),
            "cash": cash if cash is not None else 0.0,
            "total_equity": equity if equity is not None else 0.0,
        })
    return sessions


def match_trigger(
    trigger: Sequence[Sequence[Any]],
    row: Mapping[str, Any],
) -> bool:
    """Evaluate trigger clauses against an adapted session row."""
    for clause in trigger:
        field_name, op, expected = clause[0], clause[1], clause[2]
        if field_name == "vix":
            value = row.get("vix")
        elif field_name == "drawdown":
            value = row.get("unrealized_drawdown")
        elif field_name == "buy_present":
            value = row.get("buy_quantity", 0.0) > 0
        elif field_name == "sell_present":
            value = row.get("sell_quantity", 0.0) > 0
        elif field_name == "cash":
            value = row.get("cash")
        elif field_name == "exposure":
            value = row.get("exposure")
        elif field_name == "date":
            value = row.get("session")
        else:
            raise ValueError(
                f"unsupported trigger field {field_name!r}")
        if value is None:
            return False
        if op == "eq":
            ok = value == expected
        elif op == "ne":
            ok = value != expected
        elif op == "gt":
            ok = value > expected
        elif op == "gte":
            ok = value >= expected
        elif op == "lt":
            ok = value < expected
        elif op == "lte":
            ok = value <= expected
        elif op == "in":
            ok = value in expected
        elif op == "not_in":
            ok = value not in expected
        else:
            raise ValueError(f"unknown trigger operator {op!r}")
        if not ok:
            return False
    return True


def compliant_mask(
    sessions: Sequence[Mapping[str, Any]],
    normal_bound: Mapping[str, Any],
) -> List[bool]:
    """Base-compliance per session (kind-dispatched, no episode logic)."""
    kind = normal_bound["kind"]
    mask = []
    for row in sessions:
        if kind == "quantity":
            mask.append(float(row.get("buy_quantity", 0.0) or 0.0)
                        <= float(normal_bound["normal_quantity"]) + 1e-9)
        elif kind == "orders":
            mask.append(int(row.get("order_count", 0) or 0)
                        <= int(normal_bound["max_normal_orders"]))
        elif kind == "names":
            mask.append(int(row.get("names_held", 0) or 0)
                        <= int(normal_bound["max_normal_names"]))
        elif kind == "vix_calm_regime":
            vix = row.get("vix")
            mask.append(vix is not None
                        and vix <= float(normal_bound["vix_high"]))
        else:
            raise ValueError(f"unknown normal_bound kind {kind!r}")
    return mask


def protected_mask(
    sessions: Sequence[Mapping[str, Any]],
    spec_trigger: Sequence[Sequence[Any]],
    rule_type: str,
    rule_params: Mapping[str, Any],
    normal_bound: Mapping[str, Any],
) -> List[bool]:
    """Protected sessions: compliant AND outside declared repair scope.

    Declared scope = trigger match, plus armed suppression windows for
    cooldown specs (simulated deterministically on the base trace).
    Empty triggers impose no scope (compliance governs alone).
    """
    compliant = compliant_mask(sessions, normal_bound)
    horizon = (int(rule_params.get("sessions", 0))
               if rule_type == "cooldown_after_loss" else 0)
    armed: List[bool] = []
    last_arm = -10 ** 9
    for index, row in enumerate(sessions):
        if spec_trigger and match_trigger(spec_trigger, row):
            last_arm = index
        armed.append(index <= last_arm + horizon)
    protected = []
    for row, is_compliant, is_armed in zip(sessions, compliant, armed):
        if not spec_trigger:
            in_scope = False
        elif rule_type == "cooldown_after_loss":
            in_scope = is_armed
        else:
            in_scope = match_trigger(spec_trigger, row)
        protected.append(is_compliant and not in_scope)
    return protected


def block_excess(
    sessions: Sequence[Mapping[str, Any]],
    normal_quantity: float,
    block_size: int = 10,
) -> List[Dict[str, Any]]:
    """Fixed calendar-block aggregation of excess BUY quantity."""
    out = []
    for start in range(0, len(sessions), block_size):
        chunk = sessions[start:start + block_size]
        if not chunk:
            continue
        excess = sum(max(0.0, float(r.get("buy_quantity", 0.0) or 0.0)
                         - normal_quantity) for r in chunk)
        out.append({"start": start, "end": start + len(chunk) - 1,
                    "value": excess})
    return out
