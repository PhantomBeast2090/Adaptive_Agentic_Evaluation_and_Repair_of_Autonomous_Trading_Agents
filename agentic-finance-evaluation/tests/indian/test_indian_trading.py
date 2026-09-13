"""H. Action validation + I. Execution timing + J. Accounting + K. Reward."""

import pytest

from environment.indian.actions import validate_orders

def _buy(asset, instrument, qty=10.0):
    return [{"asset_id": asset, "instrument": instrument,
             "side": "BUY", "quantity": qty}]


def test_action_rejects_information_assets(fresh_env):
    for aid in ("cpi", "iip", "rbi_policy", "gsec10y", "tbill91d",
                "tbill364d", "brent", "nifty50", "indiavix", "usd_inr"):
        _, info, _, _ = fresh_env.step(
            [{"asset_id": aid, "instrument": "X", "side": "BUY", "quantity": 1.0}])
        assert info["executions"][0]["execution_status"] == "NOOP_NON_TRADEABLE_ASSET"
        assert info["executions"][0]["executed_quantity"] == 0.0
    fresh_env.reset()


def test_action_rejects_unknown_asset_and_malformed(fresh_env):
    assert validate_orders("BUY") == []
    out = validate_orders([{"asset_id": "nope", "instrument": "X",
                            "side": "BUY", "quantity": 1.0}])
    assert out[0].status == "NOOP_UNKNOWN_ASSET"
    out = validate_orders([{"asset_id": "nse_equity", "instrument": "RELIANCE",
                            "side": "BUY", "quantity": 1.0}])
    assert out[0].status == "NOOP_UNKNOWN_INSTRUMENT"
    out = validate_orders([{"asset_id": "nse_equity",
                            "instrument": "RELIANCE:EQ",
                            "side": "BUY", "quantity": -5.0}])
    assert out[0].status == "NOOP_NON_POSITIVE_QUANTITY"


def test_execution_uses_session_close_not_decision_bar(fresh_env):
    # Decision at grid[0]=2023-05-15 sees bars through 05-12; fill must be
    # at the 05-15 close (2489.25), not the visible 05-12 bar (2484.35).
    _, info, _, _ = fresh_env.step(_buy("nse_equity", "RELIANCE:EQ"))
    ex = info["executions"][0]
    assert ex["execution_status"] == "EXECUTED_FULL"
    assert ex["execution_price"] == 2489.25
    fresh_env.reset()


def test_insufficient_cash_clips_with_reason(fresh_env):
    _, info, _, _ = fresh_env.step(_buy("nse_equity", "RELIANCE:EQ", 1e9))
    ex = info["executions"][0]
    assert ex["execution_status"] == "EXECUTED_PARTIAL"
    assert ex["constraint_binding"] == "cash"
    assert ex["executed_quantity"] < 1e9
    fresh_env.reset()


def test_sell_without_position_is_noop(fresh_env):
    _, info, _, _ = fresh_env.step(
        [{"asset_id": "nse_equity", "instrument": "RELIANCE:EQ",
          "side": "SELL", "quantity": 5.0}])
    assert info["executions"][0]["execution_status"] == "NOOP_NO_POSITION"
    fresh_env.reset()


def test_realized_and_unrealized_pnl(fresh_env):
    fresh_env.step(_buy("nse_equity", "RELIANCE:EQ", 10.0))
    pos = fresh_env.snapshot_positions()
    assert pos["nse_equity:RELIANCE:EQ"]["quantity"] == 10.0
    _, info, _, _ = fresh_env.step(
        [{"asset_id": "nse_equity", "instrument": "RELIANCE:EQ",
          "side": "SELL", "quantity": 4.0}])
    assert info["executions"][0]["execution_status"] == "EXECUTED_FULL"
    assert fresh_env.portfolio.realized_pnl != 0.0
    assert fresh_env.snapshot_positions()["nse_equity:RELIANCE:EQ"]["quantity"] == 6.0
    fresh_env.reset()


def test_reward_is_portfolio_delta_incl_costs(fresh_env):
    _, info, _, _ = fresh_env.step(_buy("nse_equity", "RELIANCE:EQ", 10.0))
    fee = 10.0 * 2489.25 * 5.0 / 10000.0
    assert info["transaction_costs"] == pytest.approx(fee)
    # Immediate fill at close then mark at next visible close: pnl equals
    # mark move minus fee; recompute from reported values.
    assert info["step_pnl"] == info["portfolio_value"] - 100000.0
    assert info["cumulative_pnl"] == info["step_pnl"]
    fresh_env.reset()


def test_gold_order_fail_closed_on_unknown_calendar(fresh_env):
    _, info, _, _ = fresh_env.step(_buy("mcx_gold", "GOLDAUG2023", 1.0))
    assert info["executions"][0]["execution_status"] == "NOOP_UNKNOWN_CALENDAR"
    fresh_env.reset()


def test_terminal_and_post_terminal_semantics(fresh_env):
    done = False
    last_info = None
    while not done:
        _, last_info, done, meta = fresh_env.step([])
    assert meta["reason"] == "market_exhausted"
    _, info2, done2, meta2 = fresh_env.step([])
    assert done2 is True
    assert meta2["reason"] == "episode_already_done"
    assert info2["execution_status"] == "NOOP_EPISODE_DONE"
    fresh_env.reset()
