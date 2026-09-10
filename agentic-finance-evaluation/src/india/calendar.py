"""Authoritative NSE trading-calendar support.

The NSE holiday endpoint is the source of truth for dates downloaded into
``data/raw/india/indices``.  This module deliberately does not infer movable
holidays from month/day rules.  If a requested year is not covered by a
versioned official calendar artifact, callers must report the calendar as
unavailable rather than treating every weekday as tradable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class CalendarCoverage:
    version: str
    source: str
    covered_years: tuple[int, ...]


class NSETradingCalendar:
    """Trading dates loaded from an official NSE holiday response."""

    def __init__(
        self,
        holidays: Iterable[date],
        version: str,
        source: str,
        covered_years: Iterable[int],
    ) -> None:
        self.holidays = frozenset(holidays)
        self.coverage = CalendarCoverage(
            version=version,
            source=source,
            covered_years=tuple(sorted(set(covered_years))),
        )

    @classmethod
    def from_nse_json(cls, path: str | Path) -> "NSETradingCalendar":
        source_path = Path(path)
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        records = [
            record
            for records in payload.values()
            if isinstance(records, list)
            for record in records
            if isinstance(record, dict) and record.get("tradingDate")
        ]
        holidays = {
            datetime.strptime(record["tradingDate"], "%d-%b-%Y").date()
            for record in records
        }
        years = {holiday.year for holiday in holidays}
        return cls(
            holidays=holidays,
            version=source_path.name,
            source="NSE holiday-master?type=trading",
            covered_years=years,
        )

    def is_trading_day(self, value: date) -> bool:
        return value.weekday() < 5 and value not in self.holidays

    def trading_days(self, start: date, end: date) -> set[date]:
        if any(year not in self.coverage.covered_years for year in range(start.year, end.year + 1)):
            raise ValueError(
                f"Calendar {self.coverage.version} does not cover every year in "
                f"{start.year}..{end.year}."
            )
        result: set[date] = set()
        current = start
        while current <= end:
            if self.is_trading_day(current):
                result.add(current)
            current += timedelta(days=1)
        return result


def load_calendar(path: Optional[str | Path]) -> Optional[NSETradingCalendar]:
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    return NSETradingCalendar.from_nse_json(candidate)
