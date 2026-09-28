"""F0R repeat tests: affordability sizing, taper, config parity."""

import os

import pytest
import yaml

from agents.choice import policy as P
from agents.choice.policy import ChoiceAccumulator


def make_obs(vix, cash=100000.0, positions=None, closes=None, ts="2023-05-15"):
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
            "portfolio": {"cash": cash, "total_equity": cash, "positions": pos},
            "calendar": {"NSE_CM": "OPEN"}}


def test_unknown_policy_keys_rejected():
    with pytest.raises(ValueError):
        ChoiceAccumulator({"vix_low": 15.0, "made_up": 1})


def test_defaults_reproduce_f0_constants():
    agent = ChoiceAccumulator()
    assert agent.params["sizing_mode"] == "fixed_cash"
    assert agent.params["trend_min"] == P.TREND_MIN == -0.03
    assert agent.params["max_names_held"] == P.MAX_NAMES_HELD == 3


def test_affordability_entry_sizes_by_price():
    agent = ChoiceAccumulator({"sizing_mode": "affordability"})
    for i in range(6):  # fill trend buffer, rising
        agent.act(make_obs(12.0, closes={n: 100.0 + i
                                         for n in P.INSTRUMENTS},
                           ts=f"2023-05-{10 + i:02d}"))
    # cheap names affordable at 2 lots; pricey name only at 1
    orders = agent.act(make_obs(
        12.0, cash=3000.0,
        closes={"RELIANCE:EQ": 2500.0, "TCS:EQ": 100.0, "INFY:EQ": 100.0},
        ts="2023-05-20"))
    by_name = {o["instrument"]: o["quantity"] for o in orders
               if o["side"] == "BUY"}
    assert by_name.get("TCS:EQ") == 2.0
    assert by_name.get("INFY:EQ") == 2.0
    # RELIANCE 2*2500*1.0005+1000 = 6002.5 > 3000 -> q1 (if ordered)
    if "RELIANCE:EQ" in by_name:
        assert by_name["RELIANCE:EQ"] == 1.0


def test_adds_always_taper_to_one():
    agent = ChoiceAccumulator({"sizing_mode": "affordability"})
    for i in range(6):
        agent.act(make_obs(12.0, cash=100000.0,
                           closes={n: 100.0 + i for n in P.INSTRUMENTS},
                           ts=f"2023-05-{10 + i:02d}"))
    held = {"nse_equity:RELIANCE:EQ": 2.0}
    orders = agent.act(make_obs(
        12.0, cash=100000.0, positions=held,
        closes={n: 200.0 for n in P.INSTRUMENTS}, ts="2023-05-20"))
    adds = [o for o in orders if o["side"] == "BUY"
            and o["instrument"] == "RELIANCE:EQ"]
    assert adds and all(o["quantity"] == 1.0 for o in adds)


def test_f0r_config_parity():
    path = os.path.join(os.path.dirname(__file__), "..", "..",
                        "configs", "choice_agent", "f0r.yaml")
    cfg = yaml.safe_load(open(path))["policy"]
    assert set(cfg) - set(P.DEFAULTS) == {"vix_slot", "instruments"}
    assert cfg["sizing_mode"] == "affordability"
    assert cfg["trend_min"] == -0.05
    assert cfg["max_names_held"] == 4
    assert cfg["vix_low"] == 15.0 and cfg["vix_high"] == 25.0
    assert cfg["trend_sell"] == -0.08 and cfg["sell_q"] == 2
