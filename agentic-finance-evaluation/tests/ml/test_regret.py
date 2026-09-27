"""P2 regret tests: equation, semantics, leakage, nulls, determinism."""

import json
import os

import pytest

from evaluation.attribution import regret as RG
from evaluation.ml.diagnosis import conditional_miner as CM


def test_regret_equation_and_buy_semantics():
    assert RG.regret_of("BUY", 0.01, 0.03) == pytest.approx(0.02)
    assert RG.regret_of("BUY", -0.02, 0.01) == pytest.approx(0.03)
    assert RG.regret_adverse(0.02) is True
    assert RG.regret_adverse(0.005) is False
    assert RG.regret_adverse(0.01) is False  # strict band reuse
    assert RG.REGRET_BAND == 0.01


def test_sell_and_missing_legs_never_fabricated():
    assert RG.regret_of("SELL", 0.01, 0.03) is None
    assert RG.regret_of("HOLD", 0.01, 0.03) is None
    assert RG.regret_of("BUY", None, 0.03) is None
    assert RG.regret_of("BUY", 0.01, None) is None
    assert RG.regret_adverse(None) is None


def test_conditioning_excludes_evaluator_legs(tmp_path=None):
    ds = {"rows": [{
        "keys": {"decision_id": "d", "experiment_id": "E",
                 "decision_timestamp": "2023-05-15"},
        "features": {"action": "BUY", "x": 1.0,
                     "forward_return_3d": 0.5},  # smuggled outcome
        "outcomes": {"forward_return_3d": 0.01,
                     "hold_return": 0.03}}]}
    with pytest.raises(ValueError):
        RG.build_regret_table(ds)


def _v1():
    base = os.path.join(os.path.dirname(__file__), "..", "..")
    with open(os.path.join(
            base, "data", "frozen_traces", "_ml",
            "e5a_combined_v1.json")) as h:
        return json.load(h)


def test_frozen_r1_regret_distribution():
    base = os.path.join(os.path.dirname(__file__), "..", "..")
    r1 = RG.load_r1(base)
    built = RG.build_regret_table(r1, _v1())
    rows = built["rows"]
    assert len(rows) == 106
    lab = [r for r in rows if r["regret_adverse"] is not None]
    assert len(lab) == 100  # 6 missing-leg rows stay missing
    # DEGENERACY (verified finding, not an assumption): fills execute at
    # the recorded bar close, so forward_return_3d == hold_return on all
    # 100 rows and regret_3d is identically 0. The miner experiment is
    # therefore STOPPED (see report); this test pins the fact.
    assert all(r["regret_3d"] == 0.0 for r in lab)
    assert all(r["regret_adverse"] is False for r in lab)
    by_win = {}
    for r in lab:
        by_win.setdefault(r["keys"]["experiment_id"], []).append(r)
    assert set(by_win) == {"E5A-deterministic-attribution-20260926",
                           "E5A-window2-20260926",
                           "E5A-window3-20260926"}
    # determinism: rebuild identical
    again = RG.build_regret_table(r1, _v1())
    assert again == built


def test_miner_accepts_r1_columns_and_reports_rejections():
    base = os.path.join(os.path.dirname(__file__), "..", "..")
    r1 = RG.load_r1(base)
    built = RG.build_regret_table(r1, _v1())
    tr = [r for r in built["rows"]
          if r["keys"]["experiment_id"]
          == "E5A-deterministic-attribution-20260926"]
    mrows = [{"keys": r["keys"], "features": r["features"],
              "outcome": r["regret_adverse"]} for r in tr]
    num = [c for c in r1["rows"][0]["features"]]
    res = CM.mine(mrows, mrows, mrows, target="regret_3d",
                  numeric_columns=tuple(num),
                  categorical_columns=("rbi_stance",))
    assert res["status"] == "COMPLETE"
    assert res["spec"]["numeric_columns"] == list(num)
    assert res["n_universe"] > 0


def test_regret_module_has_no_repair_surface():
    import ast
    src = open(RG.__file__).read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = ([a.name for a in node.names] if isinstance(
                node, ast.Import) else [node.module or ""])
            for n in names:
                assert "MemoryStore" not in n and "gate" not in n, n
    for token in ("MemoryStore.admit", ".adapt(", "TargetObservation(",
                  "LearnedContext("):
        assert token not in src, token
