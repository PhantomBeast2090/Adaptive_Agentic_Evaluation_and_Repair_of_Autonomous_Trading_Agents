"""Tests for market windowing and the market fingerprint.

Windowing is what allows distinct static scenarios to be drawn from one split
file without copying or mutating data.
"""

import pandas as pd
import pytest

from environment.core import FinancialEnvironment
from environment.market.historical import HistoricalMarket


def _write_market(tmp_path, periods=10, name="market.parquet"):
    dates = pd.date_range("2020-01-01", periods=periods, freq="D")
    df = pd.DataFrame(
        {
            "SPY": [100.0 + i for i in range(periods)],
            "^VIX": [15.0 + i for i in range(periods)],
        },
        index=dates,
    )
    df.index.name = "Date"
    path = tmp_path / name
    df.to_parquet(path)
    return str(path)


def test_no_window_replays_whole_file(tmp_path):
    market = HistoricalMarket(_write_market(tmp_path))

    assert len(market.df) == 10
    assert market.window_start_date == "2020-01-01"
    assert market.window_end_date == "2020-01-10"
    assert market.max_steps == 9


def test_window_bounds_are_inclusive(tmp_path):
    market = HistoricalMarket(
        _write_market(tmp_path), start_date="2020-01-03", end_date="2020-01-05"
    )

    assert len(market.df) == 3
    assert market.window_start_date == "2020-01-03"
    assert market.window_end_date == "2020-01-05"
    assert market.reset()["market_price"] == 102.0
    assert market.max_steps == 2


def test_open_ended_windows_are_supported(tmp_path):
    path = _write_market(tmp_path)

    from_start = HistoricalMarket(path, end_date="2020-01-02")
    to_end = HistoricalMarket(path, start_date="2020-01-09")

    assert len(from_start.df) == 2
    assert from_start.window_end_date == "2020-01-02"
    assert len(to_end.df) == 2
    assert to_end.window_start_date == "2020-01-09"


def test_window_replay_visits_only_window_rows(tmp_path):
    market = HistoricalMarket(
        _write_market(tmp_path), start_date="2020-01-04", end_date="2020-01-06"
    )

    prices = [market.reset()["market_price"]]
    done = False
    while not done:
        obs, done = market.step()
        if obs is not None:
            prices.append(obs["market_price"])

    assert prices == [103.0, 104.0, 105.0]


def test_non_trading_day_bounds_clip_to_available_rows(tmp_path):
    dates = [pd.Timestamp("2020-01-03"), pd.Timestamp("2020-01-06")]
    df = pd.DataFrame({"SPY": [100.0, 101.0], "^VIX": [15.0, 16.0]}, index=dates)
    path = tmp_path / "sparse.parquet"
    df.to_parquet(path)

    market = HistoricalMarket(str(path), start_date="2020-01-04", end_date="2020-01-07")

    assert len(market.df) == 1
    assert market.window_start_date == "2020-01-06"


def test_empty_window_raises_instead_of_silently_replaying_everything(tmp_path):
    with pytest.raises(ValueError, match="selects no rows"):
        HistoricalMarket(
            _write_market(tmp_path), start_date="2021-01-01", end_date="2021-02-01"
        )


def test_reversed_window_raises(tmp_path):
    with pytest.raises(ValueError, match="must not be after"):
        HistoricalMarket(
            _write_market(tmp_path), start_date="2020-01-05", end_date="2020-01-02"
        )


def test_data_validation_runs_before_windowing(tmp_path):
    dates = pd.date_range("2020-01-01", periods=3)
    df = pd.DataFrame({"SPY": [100.0, 0.0, 102.0], "^VIX": [15.0, 16.0, 17.0]}, index=dates)
    path = tmp_path / "bad.parquet"
    df.to_parquet(path)

    # The invalid row sits outside the requested window and must still be caught.
    with pytest.raises(ValueError, match="non-positive"):
        HistoricalMarket(str(path), start_date="2020-01-03", end_date="2020-01-03")


def test_fingerprint_is_stable_and_window_specific(tmp_path):
    path = _write_market(tmp_path)

    a = HistoricalMarket(path, start_date="2020-01-02", end_date="2020-01-05")
    b = HistoricalMarket(path, start_date="2020-01-02", end_date="2020-01-05")
    c = HistoricalMarket(path, start_date="2020-01-03", end_date="2020-01-05")

    assert a.fingerprint() == b.fingerprint()
    assert a.fingerprint() != c.fingerprint()
    assert len(a.fingerprint()) == 64


def test_fingerprint_matches_across_identical_copies(tmp_path):
    first = _write_market(tmp_path, name="first.parquet")
    second = _write_market(tmp_path, name="second.parquet")

    assert HistoricalMarket(first).fingerprint() == HistoricalMarket(second).fingerprint()


def test_environment_window_shortens_the_episode(tmp_path):
    path = _write_market(tmp_path)

    env = FinancialEnvironment(
        path,
        initial_cash=1000.0,
        transaction_cost_bps=0.0,
        start_date="2020-01-02",
        end_date="2020-01-04",
    )
    obs = env.reset()
    assert obs["date"] == "2020-01-02"

    dates = [obs["date"]]
    done = False
    while not done:
        next_obs, outcome, done, _ = env.step("HOLD", 0.0)
        dates.append(outcome["date"])

    assert dates == ["2020-01-02", "2020-01-03", "2020-01-04", "2020-01-04"]


def test_environment_spec_records_window_and_fingerprint(tmp_path):
    path = _write_market(tmp_path)
    env = FinancialEnvironment(
        path,
        initial_cash=5000.0,
        transaction_cost_bps=5.0,
        start_date="2020-01-02",
        end_date="2020-01-04",
    )

    spec = env.spec()

    assert spec["window_start_date"] == "2020-01-02"
    assert spec["window_end_date"] == "2020-01-04"
    assert spec["market_rows"] == 3
    assert spec["initial_cash"] == 5000.0
    assert spec["transaction_cost_bps"] == 5.0
    assert spec["market_fingerprint"] == env.market.fingerprint()
