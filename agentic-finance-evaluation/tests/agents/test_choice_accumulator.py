"""ChoiceAccumulator focused tests (F0 behavioural validity).

Hand-built observations through the mapping branch; production path
(TargetObservation via invoke_act) is covered by the frozen contract
suites. No outcome tuning: all expectations derive from frozen policy
constants and the F0 gate document.
"""

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


def rising(agent, n=6, base=100.0, **kw):
    orders = []
    for i in range(n):
        closes = {name: base + i for name in P.INSTRUMENTS}
        orders = agent.act(make_obs(12.0, closes=closes,
                                    ts=f"2023-05-{10 + i:02d}", **kw))
    return orders


def test_constants_match_frozen_config():
    path = os.path.join(os.path.dirname(__file__), "..", "..",
                        "configs", "choice_agent", "f0.yaml")
    cfg = yaml.safe_load(open(path))["policy"]
    assert cfg["vix_low"] == P.VIX_LOW == 15.0
    assert cfg["vix_high"] == P.VIX_HIGH == 25.0
    assert cfg["trend_min"] == P.TREND_MIN == -0.03
    assert cfg["trend_sell"] == P.TREND_SELL == -0.08
    assert cfg["buy_q_full"] == P.BUY_Q_FULL == 2
    assert cfg["max_names_held"] == P.MAX_NAMES_HELD == 3
    assert list(cfg["instruments"]) == list(P.INSTRUMENTS)


def test_low_vix_builds_with_quantity_diversity():
    agent = ChoiceAccumulator()
    orders = rising(agent, cash=100000.0)
    assert orders, "expected BUYs after trend buffer fills"
    assert all(o["side"] == "BUY" for o in orders)
    assert all(o["quantity"] in (1.0, 2.0) for o in orders)
    assert len(orders) <= P.MAX_ORDERS_PER_SESSION
    small = ChoiceAccumulator()
    rising(small, cash=5000.0)
    assert {o["quantity"] for o in small.act(
        make_obs(12.0, cash=5000.0,
                 closes={n: 200.0 for n in P.INSTRUMENTS},
                 ts="2023-05-20"))} == {1.0}


def test_mid_vix_holds_fvol_guard():
    agent = ChoiceAccumulator()
    rising(agent)
    held = {"nse_equity:RELIANCE:EQ": 5.0}
    assert agent.act(make_obs(20.0, positions=held,
                              closes={n: 200.0 for n in P.INSTRUMENTS},
                              ts="2023-05-20")) == []


def test_high_vix_reduces_only_when_positioned():
    agent = ChoiceAccumulator()
    assert agent.act(make_obs(60.0, positions={},
                              closes={n: 200.0 for n in P.INSTRUMENTS},
                              ts="2023-05-20")) == []
    held = {"nse_equity:RELIANCE:EQ": 5.0, "nse_equity:TCS:EQ": 1.0}
    orders = agent.act(make_obs(60.0, positions=held,
                                closes={n: 200.0 for n in P.INSTRUMENTS},
                                ts="2023-05-20"))
    assert orders and all(o["side"] == "SELL" for o in orders)
    by_name = {o["instrument"]: o["quantity"] for o in orders}
    assert by_name["RELIANCE:EQ"] == pytest.approx(2.0)
    assert by_name["TCS:EQ"] == pytest.approx(1.0)  # never exceeds held


def test_missing_vix_or_cash_holds():
    agent = ChoiceAccumulator()
    assert agent.act(make_obs(None, closes={n: 100.0
                                            for n in P.INSTRUMENTS},
                              ts="2023-05-20")) == []
    with pytest.raises(TypeError):  # frozen contract rejects bad block
        agent.act({"decision_timestamp": "2023-05-20", "market": {},
                   "macro": {},
                   "portfolio": {"total_equity": 1.0, "positions": {}},
                   "calendar": {}})
    assert agent.act(make_obs(12.0, cash=0.5,
                              closes={n: 100.0 for n in P.INSTRUMENTS},
                              ts="2023-05-20")) == []


def test_weak_trend_blocks_initiation():
    agent = ChoiceAccumulator()
    for i in range(6):
        agent.act(make_obs(12.0, closes={n: 100.0 - i
                                         for n in P.INSTRUMENTS},
                           ts=f"2023-05-{10 + i:02d}"))
    assert agent.act(make_obs(12.0, closes={n: 70.0
                                            for n in P.INSTRUMENTS},
                              ts="2023-05-20")) == []


def test_deep_drawdown_triggers_exit_while_held():
    agent = ChoiceAccumulator()
    for i in range(6):
        agent.act(make_obs(12.0, closes={n: 100.0 - i
                                         for n in P.INSTRUMENTS},
                           ts=f"2023-05-{10 + i:02d}"))
    held = {"nse_equity:RELIANCE:EQ": 3.0}
    orders = agent.act(make_obs(12.0, positions=held,
                                closes={n: 60.0 for n in P.INSTRUMENTS},
                                ts="2023-05-20"))
    assert any(o["side"] == "SELL" and o["instrument"] == "RELIANCE:EQ"
               for o in orders)


def test_determinism_and_reset():
    obs_seq = [make_obs(12.0, closes={n: 100.0 + i
                                      for n in P.INSTRUMENTS},
                        ts=f"2023-05-{10 + i:02d}") for i in range(7)]
    a, b = ChoiceAccumulator(), ChoiceAccumulator()
    for o in obs_seq:
        assert a.act(o) == b.act(o)
    a.reset()
    c = ChoiceAccumulator()
    for o in obs_seq:
        assert a.act(o) == c.act(o)


def test_exposure_caps_and_max_names():
    agent = ChoiceAccumulator()
    rising(agent, base=100.0)
    held = {"nse_equity:RELIANCE:EQ": 100.0,
            "nse_equity:TCS:EQ": 100.0,
            "nse_equity:INFY:EQ": 100.0}
    # 3 names held -> MAX_NAMES blocks all new BUYs; trend positive
    # and shallow, so no exit SELLs either: expect silence.
    orders = agent.act(make_obs(12.0, positions=held,
                                closes={n: 110.0 for n in P.INSTRUMENTS},
                                ts="2023-05-20"))
    assert [o for o in orders if o["side"] == "BUY"] == []


def test_adapt_surface_for_future_delivery():
    agent = ChoiceAccumulator()
    agent.adapt({"entries": [{"context_id": "c1",
                              "failure_mechanism": "turnover",
                              "corrective_principle": "x"}]})
    assert len(agent.learned_contexts) == 1
    agent.adapt({"entries": [{"nope": True}, "junk"]})
    assert len(agent.learned_contexts) == 1
    agent.adapt({})
    assert len(agent.learned_contexts) == 1
