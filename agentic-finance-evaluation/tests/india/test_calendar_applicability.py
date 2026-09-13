"""Focused tests A: explicit calendar applicability (requires_calendar)."""

from dataclasses import replace
from datetime import date
from pathlib import Path

from src.india.experiment_intersection import (
    AssetRequirement,
    derive_intersection,
)
from src.india.historical_calendar import HistoricalCalendar
from src.india.session_resolver import SessionResolver

CANONICAL = Path("data/processed/india/calendars/historical_calendar.csv")


def _resolver():
    return SessionResolver(HistoricalCalendar.from_csv(CANONICAL))


def _pub_req(dates, avail=None, **kw):
    """Publication-style requirement: MOSPI venue, calendar explicitly off."""
    params = dict(asset_id="cpi", venue="MOSPI",
                  observation_dates=frozenset(dates),
                  availability_by_date=dict(avail or {}),
                  requires_calendar=False)
    params.update(kw)
    return AssetRequirement(**params)


def test_a1_requires_calendar_true_unknown_is_cal_unknown():
    req = AssetRequirement(asset_id="eq", venue="NSE_CM",
                           observation_dates=frozenset(["1997-11-03"]),
                           requires_calendar=True)
    res = derive_intersection(
        experiment_id="a1", requirements=[req],
        start=date(1997, 11, 3), end=date(1997, 11, 3),
        resolver=_resolver(), strict=False)
    assert res.included == []
    assert res.excluded[0].reason_code == "CAL_UNKNOWN"


def test_a2_requires_calendar_false_skips_gate_on_unknown_venue_date():
    req = _pub_req(["1997-11-03"], {"1997-11-03": "1997-11-03"})
    res = derive_intersection(
        experiment_id="a2", requirements=[req],
        start=date(1997, 11, 3), end=date(1997, 11, 3),
        resolver=_resolver(), strict=True)
    # No observation-date/availability problem and no calendar gate.
    assert res.included == [date(1997, 11, 3)]
    assert res.excluded == []


def test_a3_requires_calendar_false_missing_observation():
    req = _pub_req(["2023-05-19"], {"2023-05-19": "2023-05-19"})
    res = derive_intersection(
        experiment_id="a3", requirements=[req],
        start=date(2023, 5, 19), end=date(2023, 5, 20),
        resolver=_resolver(), strict=False)
    codes = {e.calendar_date: e.reason_code for e in res.excluded}
    assert codes[date(2023, 5, 20)] == "OBS_MISSING"
    assert res.excluded[0].calendar_state == "SKIPPED"


def test_a4_requires_calendar_false_null_availability_strict():
    req = _pub_req(["2023-05-19"], {})
    res = derive_intersection(
        experiment_id="a4", requirements=[req],
        start=date(2023, 5, 19), end=date(2023, 5, 19),
        resolver=_resolver(), strict=True)
    assert res.excluded[0].reason_code == "INFO_UNAVAILABLE"


def test_a5_requires_calendar_false_future_availability():
    req = _pub_req(["2023-05-19"], {"2023-05-19": "2023-05-22"})
    res = derive_intersection(
        experiment_id="a5", requirements=[req],
        start=date(2023, 5, 19), end=date(2023, 5, 19),
        resolver=_resolver(), strict=True)
    assert res.excluded[0].reason_code == "INFO_UNAVAILABLE"


def test_a6_requires_calendar_true_verified_holiday_closed():
    req = AssetRequirement(asset_id="eq", venue="NSE_CM",
                           observation_dates=frozenset(["2020-12-25"]),
                           requires_calendar=True)
    res = derive_intersection(
        experiment_id="a6", requirements=[req],
        start=date(2020, 12, 25), end=date(2020, 12, 25),
        resolver=_resolver(), strict=False)
    assert res.excluded[0].reason_code == "CAL_CLOSED"


def test_a7_requires_calendar_true_special_weekend_survives():
    req = AssetRequirement(asset_id="eq", venue="NSE_CM",
                           observation_dates=frozenset(["2023-11-12"]),
                           requires_calendar=True)
    res = derive_intersection(
        experiment_id="a7", requirements=[req],
        start=date(2023, 11, 12), end=date(2023, 11, 12),
        resolver=_resolver(), strict=False)
    assert res.included == [date(2023, 11, 12)]


def test_a8_venue_isolation_enforced_without_calendar_inference():
    # A CPI-style requirement on MOSPI must not inherit NSE_CM state, and
    # an NSE requirement must not resolve from non-NSE rows.
    cpi = _pub_req(["2023-11-12"], {"2023-11-12": "2023-11-12"})
    res = derive_intersection(
        experiment_id="a8", requirements=[cpi],
        start=date(2023, 11, 12), end=date(2023, 11, 12),
        resolver=_resolver(), strict=True)
    assert res.included == [date(2023, 11, 12)]
    # Same date through the NSE gate also passes (SPECIAL permits trading).
    eq = AssetRequirement(asset_id="eq", venue="NSE_CM",
                          observation_dates=frozenset(["2023-11-12"]),
                          requires_calendar=True)
    res2 = derive_intersection(
        experiment_id="a8b", requirements=[eq],
        start=date(2023, 11, 12), end=date(2023, 11, 12),
        resolver=_resolver(), strict=False)
    assert res2.included == [date(2023, 11, 12)]


def test_a9_default_is_requires_calendar_true():
    req = AssetRequirement(asset_id="eq", venue="NSE_CM",
                           observation_dates=frozenset(["1997-11-03"]))
    assert req.requires_calendar is True
    res = derive_intersection(
        experiment_id="a9", requirements=[req],
        start=date(1997, 11, 3), end=date(1997, 11, 3),
        resolver=_resolver(), strict=False)
    assert res.excluded[0].reason_code == "CAL_UNKNOWN"
    # explicit opt-out flips the same case to included
    opted = replace(req, requires_calendar=False,
                     availability_by_date={"1997-11-03": "1997-11-03"})
    res2 = derive_intersection(
        experiment_id="a9b", requirements=[opted],
        start=date(1997, 11, 3), end=date(1997, 11, 3),
        resolver=_resolver(), strict=True)
    assert res2.included == [date(1997, 11, 3)]


def test_a10_cpi_nse_experiment_not_rejected_for_mospi_calendar():
    # The motivating case: MOSPI has no trading-calendar rows by design.
    cpi = _pub_req(["2023-05-19"], {"2023-05-19": "2023-05-19"})
    eq = AssetRequirement(asset_id="eq", venue="NSE_CM",
                          observation_dates=frozenset(["2023-05-19"]),
                          requires_calendar=True)
    res = derive_intersection(
        experiment_id="a10", requirements=[eq, cpi],
        start=date(2023, 5, 19), end=date(2023, 5, 19),
        resolver=_resolver(), strict=False)
    assert res.included == [date(2023, 5, 19)]
