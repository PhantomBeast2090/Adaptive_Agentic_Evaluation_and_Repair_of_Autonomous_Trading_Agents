"""Typed multi-asset environment state with explicit missingness.

The state is NOT a flat dataframe. Market, macro, and portfolio blocks stay
separate, and every asset slot retains what/observation-date/availability/
vintage/venue/eligibility/why-absent metadata. Missing data never becomes a
bare NaN: each slot carries one of AVAILABLE | OBS_MISSING |
INFO_UNAVAILABLE | CAL_UNKNOWN | CAL_CLOSED | CONSTRAINT_FAIL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from environment.indian.information_lookup import (
    STATUS_AVAILABLE,
    AssetSlot,
)


@dataclass
class PortfolioView:
    cash: float
    positions: Dict[str, Dict[str, Any]]
    holdings_value: float
    total_equity: float
    exposure: float
    realized_pnl: float
    unrealized_pnl: float
    cumulative_costs: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cash": self.cash,
            "positions": self.positions,
            "holdings_value": self.holdings_value,
            "total_equity": self.total_equity,
            "exposure": self.exposure,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "cumulative_costs": self.cumulative_costs,
        }


@dataclass
class EnvironmentState:
    """One decision point: timestamp + market/macro/portfolio blocks."""

    decision_timestamp: str
    market: Dict[str, AssetSlot] = field(default_factory=dict)
    macro: Dict[str, AssetSlot] = field(default_factory=dict)
    portfolio: PortfolioView = None  # type: ignore[assignment]
    calendar: Dict[str, str] = field(default_factory=dict)

    def eligible(self, asset_id: str) -> bool:
        slot = self.market.get(asset_id) or self.macro.get(asset_id)
        return slot is not None and slot.status == STATUS_AVAILABLE

    def missingness(self) -> Dict[str, str]:
        out = {}
        for block in (self.market, self.macro):
            for key, slot in block.items():
                out[key] = slot.status
        return out

    def to_dict(self) -> Dict[str, Any]:
        def slot_dict(slot: AssetSlot) -> Dict[str, Any]:
            return {
                "status": slot.status,
                "venue": slot.venue,
                "observation_date": slot.observation_date,
                "availability_date": slot.availability_date,
                "vintage": slot.vintage,
                "values": dict(slot.values),
                "reason": slot.reason,
            }
        return {
            "decision_timestamp": self.decision_timestamp,
            "market": {k: slot_dict(v) for k, v in self.market.items()},
            "macro": {k: slot_dict(v) for k, v in self.macro.items()},
            "portfolio": self.portfolio.to_dict(),
            "calendar": dict(self.calendar),
        }
