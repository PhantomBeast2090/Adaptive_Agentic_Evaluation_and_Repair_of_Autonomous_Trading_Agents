"""v1.1 mechanism tests: ladder exits, pause; v1.0 behaviour pinned."""

import os

import pytest
import yaml

from agents.choice import policy as P
from agents.choice.policy import ChoiceAccumulator


def make_obs(vix, cash=100000.0, positions=None, closes=None,
             ts="2023-05-15", equity=None, exposure=0.0, holdings=0.0,
             unrealized=0.0):
    market = {}
    if vix is not None:
        market["indiavix"] = {"status": "AVAILABLE", "values": {"close": vix}}
    for name, close in (closes or {}).items():
        market[f"nse_equity:{name}"] = {
            "status": "AVAILABLE", "values": {"close": close}}
    pos = {}
    for k, q in (positions or {}).items():
        pos[k] = {"quantity": q}
    return {"decision_timestamp": ts,
            "market": market, "macro": {},
            "portfolio": {"cash": cash,
                          "total_equity": cash if equity is None else equity,
                          "positions": pos, "holdings_value": holdings,
                          "exposure": exposure,
                          "unrealized_pnl": unrealized},
            "calendar": {"NSE_CM": "OPEN"}}


def v11(**over):
    params = {"sizing_mode": "affordability", "trend_min": -0.05,
              "max_names_held": 4}
    params.update(over)
    return ChoiceAccumulator(params, policy_version="1.1")


def test_v11_identity_and_unknown_version():
    assert v11().identity.version == "1.1"
    assert ChoiceAccumulator().identity.version == "1.0"
    with pytest.raises(ValueError):
        ChoiceAccumulator(policy_version="9.9")


def test_v10_path_unchanged_by_v11_code():
    a = ChoiceAccumulator()
    for i in range(7):
        o = a.act(make_obs(12.0, closes={n: 100.0 + i
                                         for n in P.INSTRUMENTS},
                           ts=f"2023-05-{10 + i:02d}"))
    assert all(x["side"] == "BUY" for x in o)
    assert a.policy_version == "1.0"
    assert a.params["sizing_mode"] == "fixed_cash"


def test_staged_trim_before_flatten():
    agent = v11()
    # establish equity peak 100k, then -6% drawdown with LOW vix
    agent.act(make_obs(12.0, cash=100000.0, equity=100000.0,
                       closes={n: 100.0 for n in P.INSTRUMENTS},
                       ts="2023-05-10"))
    held = {"nse_equity:RELIANCE:EQ": 4.0}
    orders = agent.act(make_obs(
        12.0, cash=90000.0, equity=94000.0, positions=held,
        closes={n: 100.0 for n in P.INSTRUMENTS}, ts="2023-05-11"))
    trims = [o for o in orders if o["side"] == "SELL"]
    assert trims and all(o["quantity"] == 1.0 for o in trims)
    # deeper drawdown -> flatten
    orders = agent.act(make_obs(
        12.0, cash=90000.0, equity=85000.0, positions=held,
        closes={n: 100.0 for n in P.INSTRUMENTS}, ts="2023-05-12"))
    flat = [o for o in orders if o["side"] == "SELL"
            and o["instrument"] == "RELIANCE:EQ"]
    assert flat and flat[0]["quantity"] == pytest.approx(4.0)


def test_cash_pause_blocks_only_new_buys():
    agent = v11()
    for i, cash in enumerate([100000.0, 90000.0, 80000.0, 70000.0,
                              60000.0, 40000.0]):
        agent.act(make_obs(12.0, cash=cash, equity=100000.0,
                           closes={n: 100.0 + i for n in P.INSTRUMENTS},
                           ts=f"2023-05-{10 + i:02d}"))
    # cash fell 60% over window with rising closes: new BUYs paused
    assert agent.act(make_obs(
        12.0, cash=40000.0, equity=100000.0,
        closes={n: 200.0 for n in P.INSTRUMENTS},
        ts="2023-05-20")) == []


def test_ladder_brake_and_concentration_taper():
    agent = v11()
    for i in range(6):
        agent.act(make_obs(12.0, cash=100000.0, equity=100000.0,
                           closes={n: 100.0 + i for n in P.INSTRUMENTS},
                           ts=f"2023-05-{10 + i:02d}"))
    # exposure 0.6 -> brake: no new BUYs even with trend + cash
    assert agent.act(make_obs(
        12.0, cash=90000.0, equity=100000.0, exposure=0.6,
        closes={n: 200.0 for n in P.INSTRUMENTS},
        ts="2023-05-20")) == []


def test_f3_config_parity():
    path = os.path.join(os.path.dirname(__file__), "..", "..",
                        "configs", "choice_agent", "f3.yaml")
    cfg = yaml.safe_load(open(path))
    assert cfg["agent"]["policy_version"] == "1.1"
    policy = cfg["policy"]
    assert policy["exp_tier_full"] == P.EXP_TIER_FULL == 0.25
    assert policy["exp_tier_halt"] == P.EXP_TIER_HALT == 0.5
    assert policy["conc_cap"] == P.CONC_CAP == 0.4
    assert policy["dd_trim"] == P.DD_TRIM == -0.05
    assert policy["dd_flatten"] == P.DD_FLATTEN == -0.10
    assert policy["cash_drop"] == P.CASH_DROP == 0.20
    assert policy["cash_window"] == P.CASH_WINDOW == 5
    assert policy["trend_min"] == -0.05
