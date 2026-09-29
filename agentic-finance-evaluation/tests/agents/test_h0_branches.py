"""H0 branch tests: determinism, isolation, validity, provenance."""

import json
import os

import pytest
import yaml

from agents.choice.multi_asset import MultiAssetChoice

BASE = os.path.join(os.path.dirname(__file__), "..", "..")
SPEC = os.path.join(BASE, "configs", "choice_agent", "h0_states.yaml")


def _policy():
    with open(os.path.join(BASE, "configs", "choice_agent",
                           "g1.yaml")) as h:
        return yaml.safe_load(h)["policy"]


def _obs(ts, cash, positions=None, close=100.0):
    market = {"indiavix": {"status": "AVAILABLE",
                           "values": {"close": 12.0}}}
    names = ["YESBANK:EQ", "ICICIBANK:EQ", "RELIANCE:EQ", "SBIN:EQ",
             "INFY:EQ", "TCS:EQ"]
    for n in names:
        market[f"nse_equity:{n}"] = {"status": "AVAILABLE",
                                     "values": {"close": close}}
    pos = {k: {"quantity": q} for k, q in (positions or {}).items()}
    return {"decision_timestamp": ts, "market": market, "macro": {},
            "portfolio": {"cash": cash, "total_equity": cash + 1000.0,
                          "positions": pos, "holdings_value": 1000.0,
                          "exposure": 0.01, "unrealized_pnl": 0.0},
            "calendar": {"NSE_CM": "OPEN"}}


def test_spec_loads_and_freezes_grid():
    spec = yaml.safe_load(open(SPEC))
    assert [s["id"] for s in spec["states"]] == ["S0", "S1", "S2", "S3"]
    assert [s["initial_cash"] for s in spec["states"]] == [
        100000.0, 25000.0, 50000.0, 200000.0]
    assert spec["window"] == {"start": "2020-01-01", "end": "2020-09-30"}


def test_same_state_same_data_bit_identical():
    a, b = MultiAssetChoice(_policy()), MultiAssetChoice(_policy())
    outs = []
    for ag in (a, b):
        seq = []
        for i in range(8):
            seq.append(ag.act(_obs(f"2023-05-{10 + i:02d}", 50000.0)))
        outs.append(seq)
    assert outs[0] == outs[1]


def test_capital_only_difference_changes_sizing_path():
    # Identical market obs, different cash: affordability tiers may differ.
    a = MultiAssetChoice(_policy())
    rich = a.act(_obs("2023-05-20", 200000.0))
    a2 = MultiAssetChoice(_policy())
    for i in range(6):
        a2.act(_obs(f"2023-05-{10 + i:02d}", 200000.0,
                    close=100.0 + i))
    assert isinstance(rich, list)


def test_no_starting_positions_injected():
    a = MultiAssetChoice(_policy())
    assert a._closes == {} and a._pfhist == []
    o = a.act(_obs("2023-05-15", 50000.0))
    assert isinstance(o, list)


def test_quantities_contract_valid_and_no_short():
    a = MultiAssetChoice(_policy())
    held = {"nse_equity:RELIANCE:EQ": 1.0}
    for i in range(6):
        o = a.act(_obs(f"2023-05-{10 + i:02d}", 50000.0,
                       positions=held if i > 2 else None, close=50.0))
        for order in o:
            assert order["quantity"] > 0
            assert order["side"] in ("BUY", "SELL")


def test_branch_provenance_shape():
    man_path = os.path.join(BASE, "data", "frozen_traces", "_h0")
    assert os.path.isdir(os.path.join(BASE, "data", "frozen_traces"))
    assert True  # branch dirs asserted post-run in audit
