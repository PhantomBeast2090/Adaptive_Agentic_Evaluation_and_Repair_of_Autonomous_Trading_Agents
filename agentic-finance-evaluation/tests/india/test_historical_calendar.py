"""Focused tests: canonical historical calendar (uniqueness, conflicts, rebuild)."""

import csv
from datetime import date
from pathlib import Path

from src.india.historical_calendar import (
    CANONICAL_CALENDAR_COLUMNS,
    HistoricalCalendar,
    HistoricalCalendarRecord,
    validate_record,
)

CANONICAL = Path("data/processed/india/calendars/historical_calendar.csv")


def _rec(venue="NSE_CM", day="2024-05-18", **kw):
    base = dict(
        venue=venue, calendar_date=date.fromisoformat(day),
        session_type="special_weekend", market_status="SPECIAL",
        special_session=True, evidence_status="VERIFIED",
        source_file="X.pdf",
    )
    base.update(kw)
    return HistoricalCalendarRecord(**base)


def test_canonical_calendar_exists_with_stable_schema():
    assert CANONICAL.exists(), "canonical calendar must be built before tests"
    with open(CANONICAL, newline="", encoding="utf-8") as h:
        reader = csv.DictReader(h)
        assert reader.fieldnames == CANONICAL_CALENDAR_COLUMNS
        rows = list(reader)
    assert len(rows) > 0
    # stable sort by (venue, calendar_date)
    keys = [(r["venue"], r["calendar_date"]) for r in rows]
    assert keys == sorted(keys)


def test_calendar_date_uniqueness_per_venue():
    cal = HistoricalCalendar.from_csv(CANONICAL)
    assert cal.conflicts == []
    assert cal.validate() == []


def test_duplicate_identical_source_rows_dedup():
    cal = HistoricalCalendar([_rec(), _rec()])
    assert len(cal.to_rows()) == 1
    assert cal.conflicts == []


def test_conflicting_source_rows_are_blocked_not_resolved():
    cal = HistoricalCalendar([
        _rec(session_type="holiday", market_status="CLOSED", special_session=False),
        _rec(session_type="special_weekend", market_status="SPECIAL",
             special_session=True),
    ])
    assert len(cal.conflicts) == 1
    assert any("CONFLICT" in e for e in cal.validate())


def test_record_validation_rejects_bad_enums_and_half_day_invention():
    bad = _rec(session_type="half_day", market_status="SPECIAL")
    assert validate_record(bad) != []
    bad2 = _rec(venue="INDIA")
    assert validate_record(bad2) != []
    # half-day requires explicit HALF_DAY status + evidence; invented ones fail
    good_half = _rec(session_type="half_day", market_status="HALF_DAY")
    assert validate_record(good_half) == []


def test_verified_rows_cite_source_file():
    assert validate_record(_rec(evidence_status="VERIFIED", source_file="")) != []


def test_deterministic_rebuild_is_byte_identical(tmp_path):
    cal = HistoricalCalendar.from_csv(CANONICAL)
    first = tmp_path / "a.csv"
    second = tmp_path / "b.csv"
    _, sha1 = cal.to_csv(first)
    _, sha2 = HistoricalCalendar.from_csv(first).to_csv(second)
    assert sha1 == sha2
    assert first.read_bytes() == second.read_bytes()
    # canonical file hash matches a fresh serialization of its own content
    _, sha3 = HistoricalCalendar.from_csv(CANONICAL).to_csv(tmp_path / "c.csv")
    assert sha3 == HistoricalCalendar.sha256_of_file(CANONICAL)


def test_historical_boundaries_and_unknown_periods():
    cal = HistoricalCalendar.from_csv(CANONICAL)
    start, end, n = cal.coverage("NSE_CM")
    assert start == date(2019, 1, 1)  # first day of first acquired circular year
    assert end == date(2026, 12, 31)
    assert n > 2500
    # pre-acquisition history has no rows -> resolves UNKNOWN, never invented
    assert cal.get("NSE_CM", date(1997, 11, 3)) is None
    # 2024 base circular missing -> unevidenced 2024 dates stay UNKNOWN
    assert cal.get("NSE_CM", date(2024, 6, 1)) is None
    assert cal.get("RBI_FX", date(2020, 1, 2)) is None
    assert cal.get("EIA", date(2020, 1, 2)) is None


def test_no_silent_filling_no_silent_deletion():
    cal = HistoricalCalendar.from_csv(CANONICAL)
    # every row must carry evidence + source trail (or explicit DERIVED note)
    for row in cal.to_rows():
        assert row["evidence_status"] in ("VERIFIED", "DERIVED", "UNKNOWN", "CONFLICT")
        if row["evidence_status"] == "VERIFIED":
            assert row["source_file"], f"VERIFIED row lacks source: {row}"
