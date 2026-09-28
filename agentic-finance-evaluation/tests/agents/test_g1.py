"""G1 multi-asset tests: rotation, universe, parity, determinism."""

import os

import pytest
import yaml

from agents.choice import policy as P
from agents.choice.multi_asset import (
    G1_DEFAULTS, G1_INSTRUMENTS, MultiAssetChoice, ROTATION_EDGE,
)


def make_obs(vix, cash=100000.0, positions=None, closes=None,
             ts="2023-05-15", equity=None, exposure=0.0):
    market = {}
    if vix is not None:
        market["indiavix"] = {"status": "AVAILABLE", "values": {"close": vix}}
    for name, close in (closes or {}).items():
        market[f"nse_equity:{name}"] = {
            "status": "AVAILABLE", "values": {"close": close}}
    pos = {k: {"quantity": q} for k, q in (positions or {}).items()}
    return {"decision_timestamp": ts, "market": market, "macro": {},
            "portfolio": {"cash": cash,
                          "total_equity": cash if equity is None else equity,
                          "positions": pos, "holdings_value": 0.0,
                          "exposure": exposure, "unrealized_pnl": 0.0},
            "calendar": {"NSE_CM": "OPEN"}}


def base_params():
    with open(os.path.join(os.path.dirname(__file__), "..", "..",
                           "configs", "choice_agent", "g1.yaml")) as h:
        return yaml.safe_load(h)["policy"]


def test_identity_and_universe():
    a = MultiAssetChoice(base_params())
    assert a.identity.agent_id == "multi-asset-choice"
    assert len(a.names) == 6
    assert set(a.names) == set(G1_INSTRUMENTS)
    assert a.params["rotation_edge"] == ROTATION_EDGE == 0.02


def test_rotation_replaces_weakest_on_edge():
    a = MultiAssetChoice(base_params())
    # fill buffers: A rising weakly, B falling
    for i in range(6):
        a.act(make_obs(12.0, closes={"YESBANK:EQ": 100.0 + 0.1 * i,
                                     "ICICIBANK:EQ": 100.0 - i,
                                     "RELIANCE:EQ": 100.0 + 5 * i,
                                     "SBIN:EQ": 100.0 + 5 * i,
                                     "INFY:EQ": 100.0 + 5 * i,
                                     "TCS:EQ": 100.0 + 5 * i},
                        ts=f"2023-05-{10 + i:02d}"))
    held = {"nse_equity:ICICIBANK:EQ": 2.0,
            "nse_equity:RELIANCE:EQ": 2.0,
            "nse_equity:SBIN:EQ": 2.0,
            "nse_equity:INFY:EQ": 2.0}  # capped at 4
    orders = a.act(make_obs(12.0, positions=held,
                            closes={"YESBANK:EQ": 200.0,
                                    "ICICIBANK:EQ": 90.0,
                                    "RELIANCE:EQ": 200.0,
                                    "SBIN:EQ": 200.0, "INFY:EQ": 200.0,
                                    "TCS:EQ": 200.0},
                            ts="2023-05-20"))
    sides = {(o["instrument"], o["side"]) for o in orders}
    assert ("ICICIBANK:EQ", "SELL") in sides  # weakest rotated out
    assert ("YESBANK:EQ", "BUY") in sides  # vacant slot filled


def test_no_rotation_without_edge():
    a = MultiAssetChoice(base_params())
    for i in range(6):
        a.act(make_obs(12.0, closes={n: 100.0 + i for n in G1_INSTRUMENTS},
                       ts=f"2023-05-{10 + i:02d}"))
    held = {"nse_equity:RELIANCE:EQ": 2.0,
            "nse_equity:TCS:EQ": 2.0,
            "nse_equity:INFY:EQ": 2.0,
            "nse_equity:SBIN:EQ": 2.0}
    orders = a.act(make_obs(12.0, positions=held,
                            closes={n: 200.0 for n in G1_INSTRUMENTS},
                            ts="2023-05-20"))
    # capped: no rotation entries for unheld names, no rotation SELLs
    # (adds to already-held names remain legitimate accumulation)
    assert not [o for o in orders if o["instrument"] in ("YESBANK:EQ",
                                                         "ICICIBANK:EQ")]
    assert not [o for o in orders if o["side"] == "SELL"]


def test_g1_config_parity():
    p = base_params()
    assert p["max_names_held"] == 4
    assert p["max_orders_per_session"] == 6
    assert p["trend_min"] == -0.05
    assert set(p["instruments"]) == set(G1_INSTRUMENTS)


def test_determinism():
    seq = [make_obs(12.0, closes={n: 100.0 + i for n in G1_INSTRUMENTS},
                    ts=f"2023-05-{10 + i:02d}") for i in range(8)]
    a, b = MultiAssetChoice(base_params()), MultiAssetChoice(base_params())
    for o in seq:
        assert a.act(o) == b.act(o)
