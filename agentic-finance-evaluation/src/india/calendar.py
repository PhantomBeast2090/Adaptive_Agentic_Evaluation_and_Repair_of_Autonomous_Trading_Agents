"""Authoritative NSE trading-calendar support (compatibility layer).

The NSE holiday endpoint is the source of truth for dates downloaded into
``data/raw/india/indices``.  This module deliberately does not infer movable
holidays from month/day rules.  If a requested year is not covered by a
versioned official calendar artifact, callers must report the calendar as
unavailable rather than treating every weekday as tradable.

DEPRECATION NOTICE (historical-calendar milestone):
``is_trading_day`` / ``is_likely_indian_trading_day`` / ``expected_trading_days``
encode a Monday-Friday heuristic. That heuristic is retained ONLY for
backwards compatibility with the single-year 2026 artifact and MUST NOT
define historical truth. Historical session questions must go through
``src.india.historical_calendar.HistoricalCalendar`` +
``src.india.session_resolver.SessionResolver``, which return explicit
UNKNOWN for dates without official evidence and correctly preserve
weekend special sessions (e.g. 2019-10-27, 2020-11-14, 2024-01-20,
2024-05-18). New code must not call the weekday heuristic for history.
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


@dataclass(frozen=True)
class CalendarEvent:
    calendar_year: int
    market_segment: str
    trading_date: date
    description: str


class NSETradingCalendar:
    """Trading dates loaded from an official NSE holiday response."""

    def __init__(
        self,
        holidays: Iterable[date],
        version: str,
        source: str,
        covered_years: Iterable[int],
        events: Iterable[CalendarEvent] = (),
    ) -> None:
        self.holidays = frozenset(holidays)
        self.events = tuple(events)
        self.coverage = CalendarCoverage(
            version=version,
            source=source,
            covered_years=tuple(sorted(set(covered_years))),
        )

    @classmethod
    def from_nse_json(cls, path: str | Path) -> "NSETradingCalendar":
        source_path = Path(path)
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        events = cls.normalize_nse_events(payload)
        holidays = {event.trading_date for event in events}
        years = {holiday.year for holiday in holidays}
        return cls(
            holidays=holidays,
            version=source_path.name,
            source="NSE holiday-master?type=trading",
            covered_years=years,
            events=events,
        )

    @staticmethod
    def normalize_nse_events(payload: dict) -> tuple[CalendarEvent, ...]:
        """Normalize category-nested NSE records using a semantic unique key."""
        events: dict[tuple[int, str, date], CalendarEvent] = {}
        for segment, records in payload.items():
            if not isinstance(records, list):
                continue
            for record in records:
                if not isinstance(record, dict) or not record.get("tradingDate"):
                    continue
                trading_date = datetime.strptime(
                    record["tradingDate"], "%d-%b-%Y"
                ).date()
                key = (trading_date.year, str(segment), trading_date)
                events[key] = CalendarEvent(
                    calendar_year=trading_date.year,
                    market_segment=str(segment),
                    trading_date=trading_date,
                    description=str(record.get("description", "")),
                )
        return tuple(sorted(events.values(), key=lambda item: (
            item.trading_date, item.market_segment
        )))

    def is_trading_day(self, value: date) -> bool:
        """Compatibility weekday-minus-holiday predicate (DEPRECATED for history).

        Retained for the versioned 2026 artifact only. Historical session
        status must be resolved via ``SessionResolver``; this predicate
        would misclassify weekend special sessions and invent history for
        uncovered years.
        """
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


def load_calendar_directory(path: str | Path) -> Optional[NSETradingCalendar]:
    """Combine versioned annual NSE JSON artifacts without inventing years."""
    directory = Path(path)
    files = sorted(directory.glob("nse_trading_holidays_*.json"))
    if not files:
        return None
    calendars = [NSETradingCalendar.from_nse_json(file) for file in files]
    events = tuple(event for calendar in calendars for event in calendar.events)
    return NSETradingCalendar(
        holidays={event.trading_date for event in events},
        version=";".join(calendar.coverage.version for calendar in calendars),
        source="NSE holiday-master?type=trading",
        covered_years=(
            year
            for calendar in calendars
            for year in calendar.coverage.covered_years
        ),
        events=events,
    )
