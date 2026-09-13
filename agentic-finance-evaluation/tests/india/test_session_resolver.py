"""Focused tests: session resolver (specials, holidays, UNKNOWN, isolation)."""

from datetime import date
from pathlib import Path

from src.india.historical_calendar import HistoricalCalendar
from src.india.session_resolver import SessionResolver

CANONICAL = Path("data/processed/india/calendars/historical_calendar.csv")


def _resolver():
    return SessionResolver(HistoricalCalendar.from_csv(CANONICAL))


def test_four_known_nse_special_weekend_sessions():
    r = _resolver()
    for day in ("2019-10-27", "2020-11-14", "2024-01-20", "2024-05-18"):
        res = r.resolve("NSE_CM", date.fromisoformat(day))
        assert res.market_status == "SPECIAL", day
        assert res.special_session is True, day
        assert res.session_type == "special_weekend", day


def test_known_specials_are_not_weekday_rule_artifacts():
    r = _resolver()
    # all four fall on Sat/Sun; a weekday heuristic would call them closed
    for day in ("2019-10-27", "2020-11-14", "2024-01-20", "2024-05-18"):
        d = date.fromisoformat(day)
        assert d.weekday() >= 5, day  # guards the test itself
        assert r.is_special("NSE_CM", d), day


def test_verified_holidays_are_closed():
    r = _resolver()
    for day in ("2019-12-25", "2020-12-25", "2022-08-15", "2023-01-26",
                "2024-05-20", "2025-12-25"):
        res = r.resolve("NSE_CM", date.fromisoformat(day))
        assert res.market_status == "CLOSED", day


def test_unknown_preserved_for_uncovered_history():
    r = _resolver()
    res = r.resolve("NSE_CM", date(1997, 11, 3))
    assert res.market_status == "UNKNOWN"
    assert res.evidence_status == "UNKNOWN"
    # gap-year dates without evidence stay UNKNOWN (never invented)
    res = r.resolve("NSE_CM", date(2024, 6, 1))
    assert res.market_status == "UNKNOWN"


def test_missing_observation_is_not_a_holiday():
    # 30-Sep-2019: genuine bhavcopy coverage gap (mislabeled artifact).
    # 2019 is a circular-covered year and the date is a Monday, so the
    # calendar resolves regular OPEN (DERIVED) from the exhaustive holiday
    # list. The missing observation must never flip the calendar to CLOSED.
    r = _resolver()
    res = r.resolve("NSE_CM", date(2019, 9, 30))
    assert res.market_status == "OPEN"
    assert res.session_type == "regular"


def test_cross_venue_isolation():
    r = _resolver()
    # NSE specials never leak onto MCX/RBI/Brent venues
    assert r.resolve("MCX", date(2024, 5, 18)).market_status == "UNKNOWN"
    assert r.resolve("MCX", date(2024, 1, 20)).market_status == "UNKNOWN"
    assert r.resolve("RBI_FX", date(2019, 10, 27)).market_status == "UNKNOWN"
    assert r.resolve("EIA", date(2019, 10, 27)).market_status == "UNKNOWN"
    # MCX Muhurat sessions are venue-local
    assert r.resolve("MCX", date(2019, 10, 27)).market_status == "SPECIAL"
    assert r.resolve("MCX", date(2020, 11, 14)).market_status == "SPECIAL"


def test_venue_is_required():
    r = _resolver()
    try:
        r.resolve("", date(2024, 5, 18))
    except ValueError:
        pass
    else:
        raise AssertionError("empty venue must raise")


def test_mcx_morning_evening_split_noted_not_boolean():
    cal = HistoricalCalendar.from_csv(CANONICAL)
    rec = cal.get("MCX", date(2019, 10, 27))
    assert rec is not None
    assert "evening" in rec.availability_note.lower()


def test_no_half_day_without_evidence():
    cal = HistoricalCalendar.from_csv(CANONICAL)
    for row in cal.to_rows():
        assert not (row["session_type"] == "half_day"), (
            f"half-day requires official evidence: {row}")
