"""Venue-requiring session resolver over HistoricalCalendar.

The resolver answers only the market/session question:

    Was this venue open / closed / special / unknown on this date?

It never answers availability (when information became known) and never
answers eligibility (whether an agent may see an observation). Those are
handled by ``temporal_eligibility`` with a caller-supplied decision
timestamp.

Rules:

- ``venue`` is required. Cross-venue fallback is forbidden: an NSE record
  never resolves an MCX query.
- Dates without a record resolve to UNKNOWN (explicit result, not None).
- Conflicting duplicate rows for the same (venue, date) resolve to
  CONFLICT so callers fail closed instead of guessing.
- The legacy weekday heuristic from ``src.india.calendar`` is never
  consulted here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from src.india.historical_calendar import HistoricalCalendar, HistoricalCalendarRecord


@dataclass(frozen=True)
class SessionResolution:
    venue: str
    calendar_date: date
    session_type: str
    market_status: str
    special_session: bool
    evidence_status: str
    record: Optional[HistoricalCalendarRecord] = None
    reason: str = ""


class SessionResolver:
    def __init__(self, calendar: HistoricalCalendar) -> None:
        self._calendar = calendar

    @property
    def calendar(self) -> HistoricalCalendar:
        return self._calendar

    def resolve(self, venue: str, day: date) -> SessionResolution:
        if not venue:
            raise ValueError("Session resolution requires an explicit venue.")
        # Any recorded conflict for this key forces CONFLICT (fail closed).
        for first, second in self._calendar.conflicts:
            if first.venue == venue and first.calendar_date == day:
                return SessionResolution(
                    venue=venue,
                    calendar_date=day,
                    session_type="unknown",
                    market_status="CONFLICT",
                    special_session=False,
                    evidence_status="CONFLICT",
                    record=first,
                    reason=(
                        "Conflicting official evidence for this venue/date; "
                        "blocked pending reconciliation."
                    ),
                )
        record = self._calendar.get(venue, day)
        if record is None:
            return SessionResolution(
                venue=venue,
                calendar_date=day,
                session_type="unknown",
                market_status="UNKNOWN",
                special_session=False,
                evidence_status="UNKNOWN",
                record=None,
                reason="No calendar evidence for this venue/date.",
            )
        return SessionResolution(
            venue=venue,
            calendar_date=day,
            session_type=record.session_type,
            market_status=record.market_status,
            special_session=record.special_session,
            evidence_status=record.evidence_status,
            record=record,
            reason="Calendar record found.",
        )

    def is_open(self, venue: str, day: date) -> bool:
        return self.resolve(venue, day).market_status == "OPEN"

    def is_special(self, venue: str, day: date) -> bool:
        return self.resolve(venue, day).market_status == "SPECIAL"
