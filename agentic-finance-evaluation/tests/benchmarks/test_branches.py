"""Branch matrix for the volatility-threshold benchmark.

Hand-built observations only — no market episodes. Each row pins one
frozen policy clause, including boundaries, missing data, and portfolio
states. These are contract tests, never research evidence.
"""

import pytest

from benchmarks.volatility_threshold import VolatilityThresholdBenchmark

from .fixtures import FakeObservation, make_obs


def _act(agent, **kwargs):
    return agent.act(make_obs(**kwargs))


def test_low_vix_builds_both_names():
    agent = VolatilityThresholdBenchmark()
    orders = _act(agent, vix=12.5)
    assert [(o["instrument"], o["side"], o["quantity"]) for o in orders] == [
        ("RELIANCE:EQ", "BUY", 1.0),
        ("TCS:EQ", "BUY", 1.0),
    ]


def test_mid_vix_holds():
    agent = VolatilityThresholdBenchmark()
    assert _act(agent, vix=20.0) == []


def test_boundary_values_belong_to_hold():
    agent = VolatilityThresholdBenchmark()
    assert agent.act(make_obs(vix=15.0)) == []
    agent.reset()
    assert agent.act(make_obs(vix=25.0)) == []


def test_high_vix_reduces_held_names_only():
    agent = VolatilityThresholdBenchmark()
    orders = agent.act(
        make_obs(
            vix=30.0,
            positions={"nse_equity:RELIANCE:EQ": 10.0},
        )
    )
    assert orders == [
        {
            "asset_id": "nse_equity",
            "instrument": "RELIANCE:EQ",
            "side": "SELL",
            "quantity": 5.0,
        }
    ]


def test_high_vix_small_position_sells_all():
    agent = VolatilityThresholdBenchmark()
    orders = agent.act(
        make_obs(vix=30.0, positions={"nse_equity:TCS:EQ": 2.0})
    )
    assert orders[0]["quantity"] == 2.0
    assert orders[0]["side"] == "SELL"


def test_high_vix_empty_portfolio_holds():
    agent = VolatilityThresholdBenchmark()
    assert _act(agent, vix=30.0) == []


def test_missing_vix_holds():
    agent = VolatilityThresholdBenchmark()
    assert _act(agent, vix=None) == []
    assert _act(agent, vix="MISSING") == []
    assert _act(agent, vix="absent") == []
    assert _act(agent, vix="nonnumeric") == []


def test_no_cash_no_build():
    agent = VolatilityThresholdBenchmark()
    assert _act(agent, vix=10.0, cash=0.0) == []


def test_unconfigured_instruments_never_ordered():
    agent = VolatilityThresholdBenchmark()
    orders = agent.act(
        make_obs(
            vix=10.0,
            positions={"nse_equity:INFY:EQ": 7.0, "mcx_gold:GOLDAUG2023": 3.0},
        )
    )
    instruments = {o["instrument"] for o in orders}
    assert instruments <= {"RELIANCE:EQ", "TCS:EQ"}
    orders = agent.act(
        make_obs(
            vix=30.0,
            positions={"nse_equity:INFY:EQ": 7.0, "mcx_gold:GOLDAUG2023": 3.0},
        )
    )
    assert orders == []


def test_max_three_orders_per_session():
    agent = VolatilityThresholdBenchmark()
    assert len(_act(agent, vix=5.0)) <= 3


def test_invalid_observation_rejected():
    agent = VolatilityThresholdBenchmark()
    for bad in (None, "obs", 42, [], {"market": {}}, {"decision_timestamp": "x"}):
        with pytest.raises(TypeError):
            agent.act(bad)
    with pytest.raises(TypeError):
        agent.act(FakeObservation({"nope": True}))


def test_snapshot_object_accepted():
    agent = VolatilityThresholdBenchmark()
    orders = agent.act(FakeObservation(make_obs(vix=12.5)))
    assert [o["instrument"] for o in orders] == ["RELIANCE:EQ", "TCS:EQ"]


def test_reset_restores_state_and_determinism():
    agent = VolatilityThresholdBenchmark()
    first = agent.act(make_obs(vix=12.5))
    agent.act(make_obs(vix=30.0))
    agent.reset()
    assert agent.calls == 0
    assert agent.act(make_obs(vix=12.5)) == first
