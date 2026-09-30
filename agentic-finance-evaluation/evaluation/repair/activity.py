"""Generalized mechanism-relative activity flags for M-R9 (additive).

M-R7's N1 (``normality.annotate_exposure_active``) is exposure-specific.
M-R9 adjudicates five mechanisms under one fixed mechanism-relative rule,
so each mechanism needs its own PIT-safe activity predicate built from
the FROZEN detector bounds (never from candidate outcomes, economics, or
held-out data — enforced by signature: only adapted rows, mechanism
name, and bound values enter).

Hit rules mirror the frozen detectors in ``evaluation.repair.adaptive``
exactly:
- exposure:     names_held > max_normal_names
- overtrading:  order_count > max_normal_orders
- loss_chasing: previous-session reward < 0 AND buy_quantity > normal_qty
- volatility:   vix > vix_high AND buy_quantity > 0
- drawdown:     drawdown > drawdown_threshold AND buy_quantity > normal_qty

Missing/unusable fields fail closed to INACTIVE (protected, never fired
upon by the adjudication mask — preservation by default).
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

MECHANISMS = (
    "loss_chasing",
    "overtrading",
    "exposure",
    "volatility",
    "drawdown",
)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _prev_negative(sessions: List[Mapping[str, Any]], index: int) -> bool:
    if index <= 0:
        return False
    try:
        return float(sessions[index - 1].get("reward", 0.0)) < 0.0
    except (TypeError, ValueError):
        return False


def loss_chasing_active(
    sessions: List[Mapping[str, Any]], index: int, normal_qty: float
) -> bool:
    row = sessions[index]
    buy = _finite(row.get("buy_quantity", 0.0))
    if buy is None:
        return False
    return _prev_negative(sessions, index) and buy > normal_qty


def overtrading_active(row: Mapping[str, Any], max_normal_orders: int) -> bool:
    try:
        count = int(row.get("order_count", 0) or 0)
    except (TypeError, ValueError):
        return False
    return count > max_normal_orders


def exposure_active(row: Mapping[str, Any], max_normal_names: int) -> bool:
    try:
        held = int(row.get("names_held", 0) or 0)
    except (TypeError, ValueError):
        return False
    return held > max_normal_names


def volatility_active(
    row: Mapping[str, Any], vix_high: float
) -> bool:
    vix = _finite(row.get("vix", None))
    buy = _finite(row.get("buy_quantity", 0.0))
    if vix is None or buy is None:
        return False
    return vix > vix_high and buy > 0


def drawdown_active(
    row: Mapping[str, Any], drawdown_threshold: float, normal_qty: float
) -> bool:
    drawdown = _finite(row.get("drawdown", 0.0))
    buy = _finite(row.get("buy_quantity", 0.0))
    if drawdown is None or buy is None:
        return False
    return drawdown > drawdown_threshold and buy > normal_qty


def annotate_mechanism_active(
    sessions: List[Mapping[str, Any]],
    mechanism: str,
    bounds: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    """Attach ``{mechanism}_active`` flags (deterministic, diagnostic only).

    ``bounds`` carries the frozen detector parameters
    (``normal_qty`` / ``max_normal_orders`` / ``max_normal_names`` /
    ``vix_high`` / ``drawdown_threshold``). Unknown mechanism raises —
    never silently inactive.
    """
    if mechanism not in MECHANISMS:
        raise ValueError(f"unknown mechanism {mechanism!r}")
    annotated: List[Dict[str, Any]] = []
    for index, row in enumerate(sessions):
        flagged = dict(row)
        if mechanism == "loss_chasing":
            active = loss_chasing_active(
                sessions, index, float(bounds["normal_qty"]))
        elif mechanism == "overtrading":
            active = overtrading_active(
                row, int(bounds["max_normal_orders"]))
        elif mechanism == "exposure":
            active = exposure_active(
                row, int(bounds["max_normal_names"]))
        elif mechanism == "volatility":
            active = volatility_active(row, float(bounds["vix_high"]))
        elif mechanism == "drawdown":
            active = drawdown_active(
                row, float(bounds["drawdown_threshold"]),
                float(bounds["normal_qty"]))
        flagged[f"{mechanism}_active"] = bool(active)
        annotated.append(flagged)
    return annotated


def activity_flag(row: Mapping[str, Any], mechanism: str) -> bool:
    """Read a precomputed activity flag; missing fails closed to False."""
    value = row.get(f"{mechanism}_active", False)
    return value is True
