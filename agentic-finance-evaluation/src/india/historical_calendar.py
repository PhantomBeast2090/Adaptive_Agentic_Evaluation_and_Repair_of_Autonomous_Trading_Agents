"""Historical venue-isolated calendar model.

This module is the research-grade historical calendar layer. It is
deliberately separate from ``src.india.calendar.NSETradingCalendar``, which
remains the compatibility loader for the single 2026 NSE holiday JSON
artifact.

Core rules enforced here:

- Venue isolation: every record carries an explicit ``venue``. There is no
  universal "Indian trading calendar". NSE evidence never resolves MCX/RBI/
  Brent dates and vice versa.
- Date-level grain: the canonical representation is one row per
  (venue, calendar_date) unless official evidence requires otherwise.
  Intraday timings from circulars are preserved as ``session_notes``
  metadata, never as fabricated interval rows.
- UNKNOWN is first-class: any (venue, date) without a record resolves to
  UNKNOWN. Missing observations never become holidays; weekdays never imply
  open; weekends never imply closed; the 2026 artifact never extends to
  other years.
- Evidence grading: every row carries ``evidence_status`` in
  {VERIFIED, DERIVED, UNKNOWN, CONFLICT}. Secondary-source inference is
  DERIVED at best, never VERIFIED.
- Determinism: canonical CSV IO uses stable column order, stable sort by
  (venue, calendar_date), and stable serialization so the same evidence
  always produces byte-identical output plus a content SHA-256.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

CANONICAL_CALENDAR_COLUMNS = [
    "venue",
    "segment",
    "asset_class",
    "calendar_date",
    "session_type",
    "market_status",
    "special_session",
    "holiday_reason",
    "session_notes",
    "source",
    "source_url",
    "source_file",
    "retrieved_at",
    "raw_sha256",
    "evidence_status",
    "availability_note",
]

# Venue identifiers. New venues may be added only with a methodological
# reason and official evidence; never alias one venue to another.
VENUES = (
    "NSE_CM",
    "NSE_IDX",
    "MCX",
    "RBI_FX",
    "RBI_GSEC",
    "MOSPI",
    "EIA",
)

# Session types supported where officially justified.
SESSION_TYPES = (
    "regular",
    "holiday",
    "closed",
    "special_session",
    "special_weekend",
    "half_day",
    "unknown",
)

MARKET_STATUSES = (
    "OPEN",
    "CLOSED",
    "SPECIAL",
    "HALF_DAY",
    "UNKNOWN",
    "CONFLICT",
)

EVIDENCE_STATUSES = (
    "VERIFIED",
    "DERIVED",
    "UNKNOWN",
    "CONFLICT",
)


@dataclass(frozen=True)
class HistoricalCalendarRecord:
    venue: str
    calendar_date: date
    session_type: str = "unknown"
    market_status: str = "UNKNOWN"
    segment: str = ""
    asset_class: str = ""
    special_session: bool = False
    holiday_reason: str = ""
    session_notes: str = ""
    source: str = ""
    source_url: str = ""
    source_file: str = ""
    retrieved_at: str = ""
    raw_sha256: str = ""
    evidence_status: str = "UNKNOWN"
    availability_note: str = ""

    def key(self) -> Tuple[str, date]:
        return (self.venue, self.calendar_date)

    def to_row(self) -> Dict[str, str]:
        return {
            "venue": self.venue,
            "segment": self.segment,
            "asset_class": self.asset_class,
            "calendar_date": self.calendar_date.isoformat(),
            "session_type": self.session_type,
            "market_status": self.market_status,
            "special_session": "true" if self.special_session else "false",
            "holiday_reason": self.holiday_reason,
            "session_notes": self.session_notes,
            "source": self.source,
            "source_url": self.source_url,
            "source_file": self.source_file,
            "retrieved_at": self.retrieved_at,
            "raw_sha256": self.raw_sha256,
            "evidence_status": self.evidence_status,
            "availability_note": self.availability_note,
        }

    @staticmethod
    def from_row(row: Dict[str, str]) -> "HistoricalCalendarRecord":
        return HistoricalCalendarRecord(
            venue=str(row.get("venue", "")),
            calendar_date=datetime.strptime(
                str(row["calendar_date"])[:10], "%Y-%m-%d"
            ).date(),
            session_type=str(row.get("session_type", "unknown")),
            market_status=str(row.get("market_status", "UNKNOWN")),
            segment=str(row.get("segment", "")),
            asset_class=str(row.get("asset_class", "")),
            special_session=str(row.get("special_session", "false")).lower()
            == "true",
            holiday_reason=str(row.get("holiday_reason", "")),
            session_notes=str(row.get("session_notes", "")),
            source=str(row.get("source", "")),
            source_url=str(row.get("source_url", "")),
            source_file=str(row.get("source_file", "")),
            retrieved_at=str(row.get("retrieved_at", "")),
            raw_sha256=str(row.get("raw_sha256", "")),
            evidence_status=str(row.get("evidence_status", "UNKNOWN")),
            availability_note=str(row.get("availability_note", "")),
        )


def validate_record(record: HistoricalCalendarRecord) -> List[str]:
    """Return a list of validation errors; empty means valid."""
    errors: List[str] = []
    if record.venue not in VENUES:
        errors.append(f"Unknown venue: {record.venue!r}.")
    if record.session_type not in SESSION_TYPES:
        errors.append(f"Unknown session_type: {record.session_type!r}.")
    if record.market_status not in MARKET_STATUSES:
        errors.append(f"Unknown market_status: {record.market_status!r}.")
    if record.evidence_status not in EVIDENCE_STATUSES:
        errors.append(f"Unknown evidence_status: {record.evidence_status!r}.")
    # Consistency rules (additive, never inferential).
    if record.session_type in ("holiday", "closed") and record.market_status == "OPEN":
        errors.append("holiday/closed session_type cannot carry market_status OPEN.")
    if record.session_type in ("special_session", "special_weekend") and (
        not record.special_session or record.market_status != "SPECIAL"
    ):
        errors.append(
            "special sessions must set special_session=true and market_status SPECIAL."
        )
    if record.session_type == "half_day" and record.market_status != "HALF_DAY":
        errors.append("half_day session_type requires market_status HALF_DAY.")
    if record.evidence_status == "VERIFIED" and not record.source_file:
        errors.append("VERIFIED rows must cite a source_file artifact.")
    return errors


class HistoricalCalendar:
    """Venue-isolated date-level calendar with explicit UNKNOWN default."""

    def __init__(self, records: Iterable[HistoricalCalendarRecord] = ()) -> None:
        self._records: Dict[Tuple[str, date], HistoricalCalendarRecord] = {}
        self._conflicts: List[Tuple[HistoricalCalendarRecord, HistoricalCalendarRecord]] = []
        for record in records:
            self.add(record)

    def add(self, record: HistoricalCalendarRecord) -> None:
        key = record.key()
        existing = self._records.get(key)
        if existing is None:
            self._records[key] = record
            return
        if existing == record:
            return  # identical duplicate: deterministic dedup, no conflict
        # Same (venue, date) with differing content -> conflict, keep first,
        # record the disagreement for audit. Never resolve silently.
        self._conflicts.append((existing, record))

    @property
    def conflicts(self) -> List[Tuple[HistoricalCalendarRecord, HistoricalCalendarRecord]]:
        return list(self._conflicts)

    def venues(self) -> List[str]:
        return sorted({venue for venue, _ in self._records})

    def coverage(self, venue: str) -> Tuple[Optional[date], Optional[date], int]:
        dates = sorted(d for v, d in self._records if v == venue)
        if not dates:
            return (None, None, 0)
        return (dates[0], dates[-1], len(dates))

    def get(self, venue: str, day: date) -> Optional[HistoricalCalendarRecord]:
        return self._records.get((venue, day))

    def records_for_venue(self, venue: str) -> List[HistoricalCalendarRecord]:
        return sorted(
            (r for (v, _), r in self._records.items() if v == venue),
            key=lambda r: r.calendar_date,
        )

    def validate(self) -> List[str]:
        errors: List[str] = []
        for record in self._records.values():
            for error in validate_record(record):
                errors.append(f"{record.venue} {record.calendar_date}: {error}")
        for first, second in self._conflicts:
            errors.append(
                f"CONFLICT {first.venue} {first.calendar_date}: "
                f"{first.session_type}/{first.market_status} vs "
                f"{second.session_type}/{second.market_status}."
            )
        return errors

    # -- deterministic serialization -------------------------------------

    def to_rows(self) -> List[Dict[str, str]]:
        ordered = sorted(
            self._records.values(), key=lambda r: (r.venue, r.calendar_date)
        )
        return [r.to_row() for r in ordered]

    def to_csv(self, path: str | Path) -> Tuple[Path, str]:
        """Write canonical CSV deterministically; return (path, sha256)."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        rows = self.to_rows()
        with open(out, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=CANONICAL_CALENDAR_COLUMNS,
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
        digest = hashlib.sha256(out.read_bytes()).hexdigest()
        return (out, digest)

    @classmethod
    def from_csv(cls, path: str | Path) -> "HistoricalCalendar":
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            records = [HistoricalCalendarRecord.from_row(dict(row)) for row in reader]
        return cls(records)

    @staticmethod
    def sha256_of_file(path: str | Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
