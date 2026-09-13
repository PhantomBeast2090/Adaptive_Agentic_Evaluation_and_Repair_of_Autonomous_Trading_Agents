"""Master decision grid: the environment's explicit decision clock.

The grid is the set of NSE_CM sessions with market_status OPEN or SPECIAL
within [start_date, end_date], resolved through SessionResolver over the
canonical HistoricalCalendar. It is an explicitly chosen tradable-market
decision clock — NOT a universal calendar: information assets are queried
as-of each grid timestamp through temporal eligibility, never forced onto
the grid as tradable sessions.

An empty grid raises ValueError (mirroring the frozen contract: a window
selecting no rows is an error, never a silent fallback).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import List

from src.india.historical_calendar import HistoricalCalendar
from src.india.session_resolver import SessionResolver

MASTER_VENUE = "NSE_CM"
EXECUTABLE_STATUSES = ("OPEN", "SPECIAL")


def build_master_grid(
    resolver: SessionResolver,
    start: date,
    end: date,
    *,
    venue: str = MASTER_VENUE,
    include_special: bool = True,
) -> List[date]:
    """Return the ordered decision dates in [start, end] for the venue."""
    if start > end:
        raise ValueError(f"grid start {start} must not be after end {end}")
    allowed = set(EXECUTABLE_STATUSES) if include_special else {"OPEN"}
    grid: List[date] = []
    day = start
    while day <= end:
        if resolver.resolve(venue, day).market_status in allowed:
            grid.append(day)
        day += timedelta(days=1)
    if not grid:
        raise ValueError(
            f"Decision grid [{start}, {end}] selects no {venue} sessions; "
            "refusing to run on an empty clock."
        )
    return grid


def load_default_resolver(base_dir: str = ".") -> SessionResolver:
    import os
    path = os.path.join(
        base_dir, "data/processed/india/calendars/historical_calendar.csv")
    return SessionResolver(HistoricalCalendar.from_csv(path))
