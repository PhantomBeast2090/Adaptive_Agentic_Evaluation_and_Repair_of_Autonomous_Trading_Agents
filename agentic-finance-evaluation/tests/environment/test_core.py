import pytest
import os
import pandas as pd
from environment.core import FinancialEnvironment

def test_financial_environment(tmp_path):
    # Create dummy data
    dates = pd.date_range("2020-01-01", periods=5)
    df = pd.DataFrame({
        "SPY": [100.0, 105.0, 102.0, 110.0, 108.0],
        "^VIX": [20.0, 18.0, 22.0, 15.0, 16.0]
    }, index=dates)
    
    data_path = tmp_path / "dummy_data.parquet"
    df.to_parquet(data_path)
    
    env = FinancialEnvironment(str(data_path), initial_cash=10000.0, transaction_cost_bps=10.0)
    obs = env.reset()
    
    assert obs["date"] == "2020-01-01"
    assert obs["market_price"] == 100.0
    assert obs["vix"] == 20.0
    assert obs["market_data"]["market_price"] == 100.0
    assert obs["portfolio"]["cash"] == 10000.0
    
    # Step 1: BUY 10 shares at 100 = $1000 + $1 fee (10 bps of 1000 is 1000 * 0.001 = $1)
    obs, info, done, _ = env.step("BUY", 10.0)
    assert obs["market_data"]["market_price"] == 105.0
    assert obs["market_price"] == 105.0
    assert env.portfolio.holdings == 10.0
    assert env.portfolio.cash == 8999.0 # 10000 - 1000 - 1
    
    # Total value = 8999 + (10 * 105) = 10049.0
    assert obs["portfolio"]["total_value"] == 10049.0
    assert info["step_pnl"] == 49.0
    assert not done
    
    # Step 2: HOLD
    obs, info, done, _ = env.step("HOLD", 0.0)
    assert obs["market_data"]["market_price"] == 102.0
    assert obs["portfolio"]["total_value"] == 10019.0 # 8999 + 10 * 102
    assert info["step_pnl"] == -30.0
    
    # Check drawdown from peak (10049 to 10019)
    assert info["drawdown"] > 0


def test_environment_invalid_action_and_reset_after_terminal(tmp_path):
    dates = pd.date_range("2020-01-01", periods=2)
    df = pd.DataFrame({
        "SPY": [100.0, 105.0],
        "^VIX": [20.0, 21.0]
    }, index=dates)

    data_path = tmp_path / "dummy_data.parquet"
    df.to_parquet(data_path)

    env = FinancialEnvironment(str(data_path), initial_cash=1000.0, transaction_cost_bps=0.0)
    obs = env.reset()

    next_obs, info, done, _ = env.step("INVALID", 10.0)
    assert next_obs["date"] == "2020-01-02"
    assert info["step_pnl"] == 0.0
    assert env.portfolio.cash == 1000.0
    assert env.portfolio.holdings == 0.0
    assert done is False

    terminal_obs, terminal_info, done, meta = env.step("BUY", 10.0)
    assert terminal_obs["date"] == "2020-01-02"
    assert terminal_obs["portfolio"]["holdings"] == 1000.0 / 105.0
    assert terminal_info["execution_price"] == 105.0
    assert terminal_info["portfolio_value"] == 1000.0
    assert terminal_info["cash"] == 0.0
    assert terminal_info["holdings"] == 1000.0 / 105.0
    assert terminal_info["transaction_costs"] == 0.0
    assert done is True
    assert meta["reason"] == "market_exhausted"

    repeated_obs, repeated_info, done, meta = env.step("SELL", 1.0)
    assert repeated_obs["date"] == "2020-01-02"
    assert repeated_info["portfolio_value"] == 1000.0
    assert done is True
    assert meta["reason"] == "episode_already_done"

    reset_obs = env.reset()
    assert reset_obs["date"] == "2020-01-01"
    assert reset_obs["portfolio"]["cash"] == 1000.0
    assert reset_obs["portfolio"]["holdings"] == 0.0
