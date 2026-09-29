"""I1 Tier-1 tests: spec freeze, determinism, isolation, boundary bite,
contract validity, provenance. Synthetic observations only (no full runs).
"""

import os

import pytest
import yaml

from agents.choice.multi_asset import MultiAssetChoice

BASE = os.path.join(os.path.dirname(__file__), "..", "..")
SPEC_PATH = os.path.join(BASE, "configs", "choice_agent", "i1_grid.yaml")
DESIGN_PATH = os.path.join(BASE, "docs", "I1_IDENTIFIABILITY_DESIGN.md")

NAMES = ["YESBANK:EQ", "ICICIBANK:EQ", "RELIANCE:EQ", "SBIN:EQ",
         "INFY:EQ", "TCS:EQ"]


def _spec():
    with open(SPEC_PATH) as h:
        return yaml.safe_load(h)


def _base_policy():
    with open(os.path.join(BASE, "configs", "choice_agent",
                           "g1.yaml")) as h:
        return yaml.safe_load(h)["policy"]


def _cell_policy(cell_id):
    import sys
    sys.path.insert(0, os.path.join(BASE))
    from scripts.run_i1 import build_cell_policy
    spec = _spec()
    cell = next(c for c in spec["cells"] if c["id"] == cell_id)
    return build_cell_policy(_base_policy(), cell)


def _obs(ts, vix, cash=100000.0, positions=None, closes=None):
    market = {"indiavix": {"status": "AVAILABLE",
                           "values": {"close": vix}}}
    for n in NAMES:
        close = (closes or {}).get(n, 100.0)
        market[f"nse_equity:{n}"] = {"status": "AVAILABLE",
                                     "values": {"close": close}}
    pos = {f"nse_equity:{k}": {"quantity": q}
           for k, q in (positions or {}).items()}
    return {"decision_timestamp": ts, "market": market, "macro": {},
            "portfolio": {"cash": cash, "total_equity": cash + 1000.0,
                          "positions": pos, "holdings_value": 1000.0,
                          "exposure": 0.01, "unrealized_pnl": 0.0},
            "calendar": {"NSE_CM": "OPEN"}}


def _warm_trend(agent, rising=True, vix=12.0, n=7):
    for i in range(n):
        close = 100.0 + i if rising else 100.0 - i * 0.8
        agent.act(_obs(f"2023-05-{10 + i:02d}", vix,
                       closes={k: close for k in NAMES}))


# ------------------------------------------------------------ spec freeze ---

def test_spec_freezes_six_cells():
    spec = _spec()
    assert [c["id"] for c in spec["cells"]] == [
        "C0", "C1", "C2", "C3", "C4", "C5"]
    assert [(c["vix_low"], c["vix_high"], c["trend_min"])
            for c in spec["cells"]] == [
        (15.0, 25.0, -0.05), (12.0, 25.0, -0.05), (18.0, 25.0, -0.05),
        (15.0, 22.0, -0.05), (15.0, 28.0, -0.05), (15.0, 25.0, -0.03)]
    assert spec["windows"]["W1"] == {
        "start": "2020-01-01", "end": "2020-09-30",
        "role": "G1-A-equivalent-reproduction"}
    assert spec["windows"]["W2"] == {
        "start": "2021-07-01", "end": "2022-03-31",
        "role": "second-transition-window"}


def test_spec_freezes_gates_and_miner():
    spec = _spec()
    gates = spec["gates"]
    assert (gates["min_paired_contrast_train"],
            gates["min_paired_contrast_valid"],
            gates["min_paired_contrast_test"]) == (15, 10, 20)
    assert gates["min_shared_action_regimes"] == 2
    assert gates["min_contrast_instruments"] == 3
    assert gates["min_second_window_contrasts"] == 10
    miner = spec["miner_frozen"]
    assert (miner["min_train_n"], miner["min_train_delta"],
            miner["max_candidates"], miner["permutation_seed"]) == \
        (15, 0.02, 5, 20260926)
    assert "c9c9c124" in gates["reproduction_anchor_reference"]
    # Anchor correction (pre-audit, documented): full-artefact fingerprints
    # cover evaluation_id, so the anchor is behavioural-payload equality.
    assert "anchor_correction_20260928" in gates
    assert "behavioural payload" in gates["reproduction_anchor"]
    assert os.path.isfile(DESIGN_PATH)


def test_cell_policy_overrides_only_three_keys():
    base = _base_policy()
    policy = _cell_policy("C1")
    assert policy["vix_low"] == 12.0
    for key, value in base.items():
        if key in ("vix_low", "vix_high", "trend_min", "instruments"):
            continue
        assert policy[key] == value, key


def test_inverted_vix_band_rejected():
    import sys
    sys.path.insert(0, os.path.join(BASE))
    from scripts.run_i1 import build_cell_policy
    with pytest.raises(ValueError):
        build_cell_policy(_base_policy(),
                          {"id": "CX", "vix_low": 30.0, "vix_high": 25.0,
                           "trend_min": -0.05})


# ------------------------------------------------------- determinism etc. ---

def test_same_cell_same_obs_bit_identical():
    agents = [MultiAssetChoice(_cell_policy("C0")) for _ in range(2)]
    outs = []
    for agent in agents:
        seq = []
        for i in range(8):
            seq.append(agent.act(
                _obs(f"2023-05-{10 + i:02d}", 12.0,
                     closes={k: 100.0 + i for k in NAMES})))
        outs.append(seq)
    assert outs[0] == outs[1]


def test_fresh_branches_isolated_no_shared_state():
    a = MultiAssetChoice(_cell_policy("C0"))
    b = MultiAssetChoice(_cell_policy("C1"))
    assert a._closes == {} and a._pfhist == []
    assert b._closes == {} and b._pfhist == []
    assert a.params["vix_low"] == 15.0
    assert b.params["vix_low"] == 12.0


def test_unknown_policy_keys_still_rejected():
    with pytest.raises(ValueError):
        MultiAssetChoice({"bogus_key": 1.0})


# ------------------------------------------------- boundary perturbation ----

def test_low_boundary_bites_same_date():
    # VIX 14: C1 (low 12) sees MID -> HOLD; C2 (low 18) sees LOW -> BUY.
    c1, c2 = (MultiAssetChoice(_cell_policy("C1")),
              MultiAssetChoice(_cell_policy("C2")))
    _warm_trend(c1, rising=True, vix=10.0)
    _warm_trend(c2, rising=True, vix=10.0)
    o1 = c1.act(_obs("2023-05-20", 14.0,
                     closes={k: 107.0 for k in NAMES}))
    o2 = c2.act(_obs("2023-05-20", 14.0,
                     closes={k: 107.0 for k in NAMES}))
    assert o1 == []
    assert o2 and all(o["side"] == "BUY" for o in o2)


def test_high_boundary_bites_same_date():
    # VIX 24 with holdings: C3 (high 22) liquidates; C4 (high 28) holds.
    held = {"RELIANCE:EQ": 2.0}
    c3, c4 = (MultiAssetChoice(_cell_policy("C3")),
              MultiAssetChoice(_cell_policy("C4")))
    _warm_trend(c3, rising=True, vix=10.0)
    _warm_trend(c4, rising=True, vix=10.0)
    o3 = c3.act(_obs("2023-05-20", 24.0, positions=held,
                     closes={k: 107.0 for k in NAMES}))
    o4 = c4.act(_obs("2023-05-20", 24.0, positions=held,
                     closes={k: 107.0 for k in NAMES}))
    assert o3 and all(o["side"] == "SELL" for o in o3)
    assert o4 == []


def test_trend_boundary_bites_same_date():
    # Falling trend ~-3.2%: C0 (-0.05) still accumulates; C5 (-0.03) skips.
    c0, c5 = (MultiAssetChoice(_cell_policy("C0")),
              MultiAssetChoice(_cell_policy("C5")))
    for i in range(7):
        close = 100.0 - i * 0.8
        c0.act(_obs(f"2023-05-{10 + i:02d}", 12.0,
                    closes={k: close for k in NAMES}))
        c5.act(_obs(f"2023-05-{10 + i:02d}", 12.0,
                    closes={k: close for k in NAMES}))
    final = {k: 100.0 - 7 * 0.8 for k in NAMES}
    o0 = c0.act(_obs("2023-05-20", 12.0, closes=final))
    o5 = c5.act(_obs("2023-05-20", 12.0, closes=final))
    assert o0 and all(o["side"] == "BUY" for o in o0)
    assert o5 == []


def test_quantities_contract_valid_and_no_short():
    agent = MultiAssetChoice(_cell_policy("C0"))
    held = {"nse_equity:RELIANCE:EQ": 1.0}
    for i in range(8):
        obs = _obs(f"2023-05-{10 + i:02d}", 12.0,
                   positions=held if i > 3 else None,
                   closes={k: 50.0 + i for k in NAMES})
        for order in agent.act(obs):
            assert order["quantity"] > 0
            assert order["side"] in ("BUY", "SELL")


# ------------------------------------------------------------- audit units ---

def test_action_taxonomy_and_splits():
    import sys
    sys.path.insert(0, os.path.join(BASE))
    from scripts.run_i1 import action_class, split_of, c0_regime
    assert action_class({"submitted_orders": []}) == "HOLD"
    assert action_class({"submitted_orders": [{"side": "BUY"}]}) == "BUY"
    assert action_class({"submitted_orders": [{"side": "SELL"}]}) == "SELL"
    assert action_class({"submitted_orders": [{"side": "BUY"},
                                              {"side": "SELL"}]}) == "MIXED"
    spec = _spec()
    assert split_of("2020-02-15", spec) == "TRAIN"
    assert split_of("2021-11-01", spec) == "VALID"
    assert split_of("2022-02-01", spec) == "TEST"
    assert split_of("2019-01-01", spec) is None
    assert c0_regime(14.9) == "LOW"
    assert c0_regime(15.0) == "MID"
    assert c0_regime(25.0) == "MID"
    assert c0_regime(25.1) == "HIGH"


def test_spec_fingerprint_stable():
    import sys
    sys.path.insert(0, os.path.join(BASE))
    from scripts.run_i1 import spec_fingerprint
    assert spec_fingerprint(BASE) == spec_fingerprint(BASE)
