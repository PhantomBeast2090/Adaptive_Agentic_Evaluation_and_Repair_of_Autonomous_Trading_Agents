"""M. No-look-ahead probes (15). Any failure here blocks the milestone."""

import pytest

from datetime import date

from environment.indian.clock import build_master_grid
from environment.indian.information_lookup import STATUS_AVAILABLE


def _slot(env, asset, stamp, **kw):
    return env.lookup.get_information(asset, stamp, "explicit", kw or None)


def test_01_future_availability_invisible(fresh_env):
    s = _slot(fresh_env, "cpi", "2023-05-15")
    assert s.status == STATUS_AVAILABLE and s.observation_date == "2023-03-31"
    assert s.availability_date == "2023-04-12"


def test_02_null_availability_invisible_strict(fresh_env):
    assert _slot(fresh_env, "brent", "2023-05-15").status == "INFO_UNAVAILABLE"


def test_03_historical_availability_visible(fresh_env):
    s = _slot(fresh_env, "cpi", "2023-06-15")
    assert (s.status, s.observation_date) == (STATUS_AVAILABLE, "2023-05-31")


def test_04_publication_asset_not_calendar_gated(fresh_env):
    s = _slot(fresh_env, "cpi", "2023-05-15")
    assert s.status == STATUS_AVAILABLE  # MOSPI has no calendar rows


def test_05_exchange_asset_calendar_gated(fresh_env):
    # 2023-11-14 is a verified NSE holiday: gated CLOSED at resolver level.
    res = fresh_env.resolver.resolve("NSE_CM", date(2023, 11, 14))
    assert res.market_status == "CLOSED"


def test_06_nse_holiday_does_not_hide_cpi(fresh_env):
    s = _slot(fresh_env, "cpi", "2023-11-14")
    assert s.status == STATUS_AVAILABLE


def test_07_cpi_release_does_not_open_nse(fresh_env):
    # 2023-05-13 is a Saturday (no session) though macro exists: grid skips it.
    grid = build_master_grid(fresh_env.resolver, date(2023, 5, 12), date(2023, 5, 15))
    assert [d.isoformat() for d in grid] == ["2023-05-12", "2023-05-15"]


def test_08_mcx_does_not_inherit_nse(fresh_env):
    assert fresh_env.resolver.resolve("MCX", date(2023, 5, 15)).market_status == "UNKNOWN"
    assert fresh_env.resolver.resolve("NSE_CM", date(2023, 5, 15)).market_status == "OPEN"


def test_09_special_weekend_usable_where_supported(fresh_env):
    grid = build_master_grid(fresh_env.resolver, date(2023, 11, 10), date(2023, 11, 14))
    assert date(2023, 11, 12) in grid  # Muhurat special survives
    # No equity bar was published for the 1-hour session: order must fail on
    # missing price, never on calendar.
    from environment.indian.environment import IndianMultiAssetEnvironment
    from tests.indian.conftest import SMALL_CONFIG
    cfg = dict(SMALL_CONFIG)
    cfg["start_date"] = "2023-11-10"
    cfg["end_date"] = "2023-11-14"
    env = IndianMultiAssetEnvironment(cfg)
    env.reset()
    _, info, _, _ = env.step([])  # advance Fri -> Sun special
    assert info["date"] == "2023-11-12"
    _, info2, _, _ = env.step(
        [{"asset_id": "nse_equity", "instrument": "RELIANCE:EQ",
          "side": "BUY", "quantity": 1.0}])
    assert info2["executions"][0]["execution_status"] == "NOOP_NO_PRICE"


def test_10_future_observation_excluded_from_state(fresh_env):
    d = fresh_env.reset()
    assert d["market"]["nifty50"]["observation_date"] < d["decision_timestamp"]


def test_11_future_price_cannot_influence_reward(fresh_env):
    _, info, _, _ = fresh_env.step(
        [{"asset_id": "nse_equity", "instrument": "RELIANCE:EQ",
          "side": "BUY", "quantity": 10.0}])
    # Mark equals the execution-session close, never a later bar.
    assert info["executions"][0]["execution_price"] == 2489.25
    assert info["portfolio_value"] == pytest.approx(
        100000.0 - 10.0 * 2489.25 * 5.0 / 10000.0)
    fresh_env.reset()


def test_12_no_same_bar_leak_into_decision(fresh_env):
    d = fresh_env.reset()  # decision 2023-05-15
    assert d["market"]["nse_equity:RELIANCE:EQ"]["observation_date"] == "2023-05-12"
    assert d["market"]["nse_equity:RELIANCE:EQ"]["values"]["close"] == 2484.35


def test_13_missingness_reason_preserved(fresh_env):
    d = fresh_env.reset()
    assert d["macro"]["brent"]["status"] == "INFO_UNAVAILABLE"
    assert d["macro"]["brent"]["reason"] != ""


def test_14_vintage_selection_explicit(fresh_env):
    import pytest
    from src.india.experiment_intersection import build_requirement_from_frame
    import pandas as pd
    frame = pd.DataFrame({
        "observation_date": ["2023-03-31", "2023-03-31"],
        "availability_date": ["2023-04-12", "2023-05-12"]})
    with pytest.raises(ValueError, match="explicit availability_policy"):
        build_requirement_from_frame(
            asset_id="cpi", venue="MOSPI", frame=frame,
            observation_col="observation_date",
            availability_col="availability_date")


def test_15_repeated_runs_deterministic(fresh_env):
    from environment.indian.environment import IndianMultiAssetEnvironment
    from tests.indian.conftest import SMALL_CONFIG
    recueill = []
    for _ in range(2):
        env = IndianMultiAssetEnvironment(dict(SMALL_CONFIG))
        env.reset()
        trace = []
        done = False
        while not done:
            s, i, done, _ = env.step(
                [{"asset_id": "nse_equity", "instrument": "TCS:EQ",
                  "side": "BUY", "quantity": 2.0}] if not done else [])
            trace.append((s["decision_timestamp"], round(i["portfolio_value"], 6)))
        recueill.append(trace)
    assert recueill[0] == recueill[1]
