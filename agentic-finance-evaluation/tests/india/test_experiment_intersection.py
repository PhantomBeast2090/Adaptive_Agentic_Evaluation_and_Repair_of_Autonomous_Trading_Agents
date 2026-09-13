"""Focused tests: experiment-specific intersections with reason codes."""

from datetime import date
from pathlib import Path

import pandas as pd

from src.india.experiment_intersection import (
    AssetRequirement,
    build_requirement_from_frame,
    derive_intersection,
    summarize_exclusions,
)
from src.india.historical_calendar import HistoricalCalendar
from src.india.session_resolver import SessionResolver

CANONICAL = Path("data/processed/india/calendars/historical_calendar.csv")

# Covered-year fixtures (2023 has a complete annual circular):
# 2023-05-19 Fri regular OPEN, 2023-11-12 Sun Muhurat SPECIAL (VERIFIED),
# 2023-11-11 Sat weekend CLOSED, 2020-12-25 Fri holiday CLOSED.


def _resolver():
    return SessionResolver(HistoricalCalendar.from_csv(CANONICAL))


def _nse_req(dates, avail=None, **kw):
    avail = avail or {}
    return AssetRequirement(
        asset_id=kw.get("asset_id", "nse_equity"), venue="NSE_CM",
        observation_dates=frozenset(dates), availability_by_date=avail,
    )


def test_special_sessions_survive_intersection():
    req = _nse_req(["2023-11-11", "2023-11-12", "2023-11-13"],
                   asset_id="eq")
    res = derive_intersection(
        experiment_id="t1", requirements=[req],
        start=date(2023, 11, 11), end=date(2023, 11, 13),
        resolver=_resolver(), strict=False, require_open_calendar=True,
    )
    assert date(2023, 11, 12) in res.included  # Sunday Muhurat kept
    assert date(2023, 11, 13) in res.included  # Monday regular kept


def test_missing_observation_reason_code():
    req = _nse_req(["2023-11-12"], asset_id="eq")
    res = derive_intersection(
        experiment_id="t2", requirements=[req],
        start=date(2023, 11, 12), end=date(2023, 11, 13),
        resolver=_resolver(), strict=False,
    )
    codes = {e.calendar_date: e.reason_code for e in res.excluded}
    assert codes[date(2023, 11, 13)] == "OBS_MISSING"


def test_unavailable_information_reason_code():
    req = _nse_req(["2023-05-19"], {"2023-05-19": "2023-05-22"}, asset_id="eq")
    res = derive_intersection(
        experiment_id="t3", requirements=[req],
        start=date(2023, 5, 19), end=date(2023, 5, 19),
        resolver=_resolver(), strict=True,
    )
    assert res.included == []
    assert res.excluded[0].reason_code == "INFO_UNAVAILABLE"


def test_null_availability_strict_blocks():
    req = _nse_req(["2023-05-19"], {}, asset_id="eq")
    res = derive_intersection(
        experiment_id="t4", requirements=[req],
        start=date(2023, 5, 19), end=date(2023, 5, 19),
        resolver=_resolver(), strict=True,
    )
    assert res.excluded[0].reason_code == "INFO_UNAVAILABLE"


def test_cal_unknown_for_uncovered_history():
    req = _nse_req(["1997-11-03", "1997-11-04"], asset_id="eq")
    res = derive_intersection(
        experiment_id="t5", requirements=[req],
        start=date(1997, 11, 3), end=date(1997, 11, 4),
        resolver=_resolver(), strict=False,
    )
    assert {e.reason_code for e in res.excluded} == {"CAL_UNKNOWN"}


def test_cal_closed_for_verified_holiday():
    req = _nse_req(["2020-12-25"], asset_id="eq")
    res = derive_intersection(
        experiment_id="t6", requirements=[req],
        start=date(2020, 12, 25), end=date(2020, 12, 25),
        resolver=_resolver(), strict=False,
    )
    assert res.excluded[0].reason_code == "CAL_CLOSED"


def test_cross_venue_gold_gap_is_unknown_not_defect():
    # Gold has no MCX row for 2024-05-18 -> CAL_UNKNOWN (auditable),
    # never forced onto the NSE session.
    gold = AssetRequirement(asset_id="gold", venue="MCX",
                            observation_dates=frozenset(["2024-05-17"]))
    res = derive_intersection(
        experiment_id="t7", requirements=[gold],
        start=date(2024, 5, 17), end=date(2024, 5, 18),
        resolver=_resolver(), strict=False,
    )
    by_date = {e.calendar_date: e for e in res.excluded}
    assert by_date[date(2024, 5, 18)].reason_code == "CAL_UNKNOWN"
    assert by_date[date(2024, 5, 18)].venue == "MCX"


def test_experiment_specific_intersections_differ():
    dates = ["2023-11-12", "2023-11-13"]
    eq = _nse_req(dates, {}, asset_id="eq")
    gold = AssetRequirement(asset_id="gold", venue="MCX",
                            observation_dates=frozenset(dates))
    eq_only = derive_intersection(
        experiment_id="eq", requirements=[eq],
        start=date(2023, 11, 12), end=date(2023, 11, 13),
        resolver=_resolver(), strict=False)
    both = derive_intersection(
        experiment_id="both", requirements=[eq, gold],
        start=date(2023, 11, 12), end=date(2023, 11, 13),
        resolver=_resolver(), strict=False)
    assert len(eq_only.included) == 2
    # MCX has no calendar evidence for either date -> both excluded there
    assert len(both.included) == 0
    assert summarize_exclusions(both)["CAL_UNKNOWN"] == 2


def test_no_silent_deletion_every_date_accounted():
    req = _nse_req(["2023-05-19"], {}, asset_id="eq")
    res = derive_intersection(
        experiment_id="t9", requirements=[req],
        start=date(2023, 5, 19), end=date(2023, 5, 22),
        resolver=_resolver(), strict=False)
    assert len(res.included) + len(res.excluded) == 4
    for e in res.excluded:
        assert e.reason_code and e.detail


def test_decision_policy_is_caller_supplied():
    req = _nse_req(["2023-05-19"], {"2023-05-19": "2023-05-22"}, asset_id="eq")
    lagged = derive_intersection(
        experiment_id="t10", requirements=[req],
        start=date(2023, 5, 19), end=date(2023, 5, 19),
        resolver=_resolver(), strict=True,
        decision_policy=lambda d: date(2023, 5, 22))
    assert lagged.included == [date(2023, 5, 19)]


def test_build_requirement_from_canonical_frames():
    nifty = pd.read_csv("data/processed/india/market/nse_nifty_50_daily.csv",
                        usecols=["date"])
    req = build_requirement_from_frame(
        asset_id="nifty50", venue="NSE_CM", frame=nifty,
        observation_col="date")
    assert "2019-10-27" in req.observation_dates
    assert "2024-05-18" in req.observation_dates
    # no availability column -> strict intersection stays ineligible
    res = derive_intersection(
        experiment_id="t11", requirements=[req],
        start=date(2023, 5, 19), end=date(2023, 5, 19),
        resolver=_resolver(), strict=True)
    assert res.excluded and res.excluded[0].reason_code == "INFO_UNAVAILABLE"
