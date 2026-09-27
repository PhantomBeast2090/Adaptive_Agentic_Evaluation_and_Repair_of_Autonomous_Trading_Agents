"""Entry-timing benchmark tests: equation, legs, PIT, nulls, boundary."""

import json
import os

import pytest

from evaluation.attribution import timing as TM
from evaluation.attribution.engine import DecisionAttributionEngine
from evaluation.ml.diagnosis import conditional_miner as CM


def test_timing_equation_and_band():
    eng = DecisionAttributionEngine(base_dir=".")
    # exec 100, next-day 90, horizon 121: later entry wins by ~0.134
    assert TM.timing_of("BUY", 100.0, 90.0, 121.0, eng) == pytest.approx(
        (121.0 - 90.0) / 90.0 - (121.0 - 100.0) / 100.0)
    assert TM.timing_adverse(0.134) is True
    assert TM.timing_adverse(0.01) is False  # strict band reuse
    assert TM.timing_adverse(-0.05) is False
    assert TM.TIMING_BAND == 0.01


def test_sell_and_missing_legs_never_fabricated():
    eng = DecisionAttributionEngine(base_dir=".")
    assert TM.timing_of("SELL", 100.0, 90.0, 121.0, eng) is None
    assert TM.timing_of("BUY", None, 90.0, 121.0, eng) is None
    assert TM.timing_of("BUY", 100.0, None, 121.0, eng) is None
    assert TM.timing_of("BUY", 100.0, 90.0, None, eng) is None
    assert TM.timing_of("BUY", 0.0, 90.0, 121.0, eng) is None
    assert TM.timing_adverse(None) is None


def test_conditioning_excludes_evaluator_legs():
    ds = {"rows": [{
        "keys": {"decision_id": "d", "experiment_id": "E",
                 "decision_timestamp": "2023-05-15"},
        "features": {"action": "BUY", "x": 1.0, "timing_regret": 0.5},
        "outcomes": {"forward_return_3d": 0.01,
                     "hold_return": 0.03}}]}
    with pytest.raises(ValueError):
        TM.build_timing_table(ds, base_dir=".")


def test_frozen_timing_distribution():
    base = os.path.join(os.path.dirname(__file__), "..", "..")
    r1 = TM.load_r1(base)
    with open(os.path.join(
            base, "data", "frozen_traces", "_ml",
            "e5a_combined_v1.json")) as h:
        v1 = json.load(h)
    built = TM.build_timing_table(r1, v1, base_dir=base)
    rows = built["rows"]
    assert len(rows) == 106
    lab = [r for r in rows if r["timing_adverse"] is not None]
    assert 0 < len(lab) < len(rows)  # missing legs preserved, not filled
    adv = sum(1 for r in lab if r["timing_adverse"])
    assert 0 < adv < len(lab)  # non-degenerate target (else STOP)
    wins = {r["keys"]["experiment_id"] for r in lab}
    assert wins == {"E5A-deterministic-attribution-20260926",
                    "E5A-window2-20260926", "E5A-window3-20260926"}
    again = TM.build_timing_table(r1, v1, base_dir=base)
    assert again == built  # determinism


def test_miner_accepts_timing_outcome():
    base = os.path.join(os.path.dirname(__file__), "..", "..")
    r1 = TM.load_r1(base)
    with open(os.path.join(
            base, "data", "frozen_traces", "_ml",
            "e5a_combined_v1.json")) as h:
        v1 = json.load(h)
    built = TM.build_timing_table(r1, v1, base_dir=base)
    tr = [r for r in built["rows"] if r["keys"]["experiment_id"]
          == "E5A-deterministic-attribution-20260926"]
    mrows = [{"keys": r["keys"], "features": r["features"],
              "outcome": r["timing_adverse"]} for r in tr]
    num = [c for c in r1["rows"][0]["features"]]
    res = CM.mine(mrows, mrows, mrows, target="timing_regret",
                  numeric_columns=tuple(num),
                  categorical_columns=("instrument", "action",
                                       "rbi_stance",
                                       "active_context_version"))
    assert res["status"] == "COMPLETE"
    assert res["n_universe"] > 0


def test_timing_module_has_no_repair_surface():
    import ast
    src = open(TM.__file__).read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = (node.module or "") if isinstance(
                node, ast.ImportFrom) else ""
            names = [a.name for a in node.names] if isinstance(
                node, ast.Import) else []
            assert "MemoryStore" not in mod and "gate" not in mod, mod
            for n in names + ([node.module or ""] if isinstance(
                    node, ast.ImportFrom) else []):
                assert n not in ("MemoryStore", "OraclePacket",
                                 "TargetObservation"), n
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in ("adapt", "admit",
                                          "adjudicate"), node.func.attr
    for token in ("MemoryStore.admit", "LearnedContext("):
        assert token not in src, token
