import pandas as pd
import pytest

from environment.market.historical import HistoricalMarket


def _write_market_data(tmp_path, df):
    path = tmp_path / "market.parquet"
    df.to_parquet(path)
    return path


def test_market_rejects_missing_required_columns(tmp_path):
    path = _write_market_data(
        tmp_path,
        pd.DataFrame({"SPY": [100.0]}, index=pd.date_range("2020-01-01", periods=1)),
    )

    with pytest.raises(ValueError, match="missing required columns"):
        HistoricalMarket(str(path))


def test_market_rejects_unsorted_duplicate_missing_or_nonpositive_data(tmp_path):
    cases = [
        pd.DataFrame(
            {"SPY": [100.0, 101.0], "^VIX": [20.0, 21.0]},
            index=[pd.Timestamp("2020-01-02"), pd.Timestamp("2020-01-01")],
        ),
        pd.DataFrame(
            {"SPY": [100.0, 101.0], "^VIX": [20.0, 21.0]},
            index=[pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-01")],
        ),
        pd.DataFrame(
            {"SPY": [100.0, None], "^VIX": [20.0, 21.0]},
            index=pd.date_range("2020-01-01", periods=2),
        ),
        pd.DataFrame(
            {"SPY": [100.0, 0.0], "^VIX": [20.0, 21.0]},
            index=pd.date_range("2020-01-01", periods=2),
        ),
    ]

    for i, df in enumerate(cases):
        path = tmp_path / f"bad_market_{i}.parquet"
        df.to_parquet(path)
        with pytest.raises(ValueError):
            HistoricalMarket(str(path))


def test_one_timestep_market_can_reset_and_terminate(tmp_path):
    path = _write_market_data(
        tmp_path,
        pd.DataFrame(
            {"SPY": [100.0], "^VIX": [20.0]},
            index=pd.date_range("2020-01-01", periods=1),
        ),
    )

    market = HistoricalMarket(str(path))

    assert market.reset()["market_price"] == 100.0
    obs, done = market.step()
    assert obs is None
    assert done is True
