"""Shared observation readers for canonical E3 benchmarks.

All canonical benchmarks accept a ``TargetObservation`` in production.
For hand-built contract tests they also accept a plain mapping carrying
the same closed schema (``decision_timestamp``, ``market``, ``macro``,
``portfolio``, ``calendar``). Anything else — raw environment state,
strings, ``None``, mappings with missing blocks — is rejected with
``TypeError``. Values are never imputed or forward-filled: a missing or
unusable reading yields ``None`` and the caller holds.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

STATUS_AVAILABLE = "AVAILABLE"


def as_dict(observation: Any) -> Dict[str, Any]:
    """Return the observation payload as a plain dict, or raise."""
    if isinstance(observation, Mapping):
        payload = dict(observation)
    elif hasattr(observation, "to_dict") and callable(
        getattr(observation, "to_dict")
    ):
        payload = dict(observation.to_dict())
        # A TargetObservation snapshot always carries this marker block;
        # anything else arriving via to_dict() is not an observation.
        if "decision_timestamp" not in payload:
            raise TypeError(
                "observation snapshot lacks 'decision_timestamp': "
                f"{type(observation).__name__}"
            )
    else:
        raise TypeError(
            "benchmark observations must be a TargetObservation or a "
            f"mapping with the observation schema, got "
            f"{type(observation).__name__}"
        )
    for block in ("market", "macro", "portfolio"):
        if not isinstance(payload.get(block), Mapping):
            raise TypeError(
                f"observation block {block!r} must be a mapping"
            )
    portfolio = payload["portfolio"]
    for key in ("cash", "total_equity", "positions"):
        if key not in portfolio:
            raise TypeError(
                f"observation portfolio lacks {key!r}"
            )
    if not isinstance(payload.get("decision_timestamp"), str):
        raise TypeError("observation 'decision_timestamp' must be a string")
    return payload


def _finite_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def read_indicator_close(
    payload: Mapping[str, Any], slot_key: str
) -> Optional[float]:
    """Return a prior-session indicator close, or None when unusable.

    Consumes the value only when the slot status is AVAILABLE and the
    close parses as a finite number. Missing slots, non-AVAILABLE
    statuses, and empty/non-numeric values all yield None (hold).
    """
    market = payload.get("market", {})
    macro = payload.get("macro", {})
    slot = None
    if isinstance(market, Mapping) and isinstance(
        market.get(slot_key), Mapping
    ):
        slot = market[slot_key]
    elif isinstance(macro, Mapping) and isinstance(
        macro.get(slot_key), Mapping
    ):
        slot = macro[slot_key]
    if not isinstance(slot, Mapping):
        return None
    if slot.get("status") != STATUS_AVAILABLE:
        return None
    values = slot.get("values", {})
    if not isinstance(values, Mapping):
        return None
    return _finite_number(values.get("close"))


def read_positions(payload: Mapping[str, Any]) -> Dict[str, float]:
    """Return {position_key: quantity} for finite non-negative holdings."""
    portfolio = payload.get("portfolio", {})
    positions = portfolio.get("positions", {}) if isinstance(
        portfolio, Mapping
    ) else {}
    if not isinstance(positions, Mapping):
        return {}
    cleaned: Dict[str, float] = {}
    for key, slot in positions.items():
        if not isinstance(slot, Mapping):
            continue
        quantity = _finite_number(slot.get("quantity"))
        if quantity is not None and quantity > 0:
            cleaned[str(key)] = quantity
    return cleaned


def read_cash(payload: Mapping[str, Any]) -> Optional[float]:
    """Return finite cash, or None when unusable."""
    portfolio = payload.get("portfolio", {})
    if not isinstance(portfolio, Mapping):
        return None
    return _finite_number(portfolio.get("cash"))


def position_key(asset_id: str, instrument: str) -> str:
    """Environment position-key convention: ``{asset_id}:{instrument}``."""
    return f"{asset_id}:{instrument}"


def build_order(
    asset_id: str, instrument: str, side: str, quantity: float
) -> Dict[str, Any]:
    """One well-formed order mapping in the E0 order-list contract."""
    if side not in ("BUY", "SELL"):
        raise ValueError(f"side must be BUY or SELL, got {side!r}")
    if not isinstance(quantity, (int, float)) or quantity <= 0:
        raise ValueError(f"quantity must be positive, got {quantity!r}")
    return {
        "asset_id": asset_id,
        "instrument": instrument,
        "side": side,
        "quantity": float(quantity),
    }
