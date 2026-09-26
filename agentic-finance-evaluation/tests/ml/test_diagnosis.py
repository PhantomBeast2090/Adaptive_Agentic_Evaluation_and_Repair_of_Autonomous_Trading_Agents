"""Diagnostic-layer tests: miner discipline, hypothesis provenance,
validation boundary. No model-quality assertions; protocol only.
"""

import os

import pytest

from evaluation.ml.diagnosis import conditional_miner as CM
from evaluation.ml.diagnosis import forecast_diagnostics as FD
from evaluation.ml.diagnosis import hypothesis_builder as HB
from evaluation.ml.diagnosis.failure_hypothesis import (
    CANDIDATE, DiagnosticHypothesis,
)
from evaluation.ml.diagnosis import FailureHypothesis
from evaluation.ml.validation.ml_validation import validate_candidate


def _row(did, ts, win, feats, outcome):
    return {"keys": {"decision_id": did, "experiment_id": win,
                     "decision_timestamp": ts},
            "features": feats, "outcome": outcome}


def _planted_split():
    # TRAIN: f_ret_5d low band strongly enriched; VALID confirms weakly.
    train, valid, test = [], [], []
    for i in range(60):
        low = i < 20
        fret = (-0.06 + 0.001 * i) if low else (0.005 + 0.001 * i)
        train.append(_row(f"t{i}", f"2023-05-{(10 + i) % 28 + 1:02d}", "W1",
                          {"f_ret_5d": fret,
                           "f_downside_prob": 0.8 if low else 0.2,
                           "instrument": "A:EQ"},
                          True if (low or i % 7 == 0) else False))
    for i in range(40):
        low = i < 14
        fret = (-0.06 + 0.001 * i) if low else (0.005 + 0.001 * i)
        valid.append(_row(f"v{i}", f"2023-06-{(1 + i) % 28 + 1:02d}", "W2",
                          {"f_ret_5d": fret,
                           "f_downside_prob": 0.8 if low else 0.2,
                           "instrument": "A:EQ"},
                          True if (low and i % 4 != 0) or i % 9 == 0
                          else False))
    for i in range(20):
        low = i < 7
        fret = (-0.06 + 0.001 * i) if low else (0.005 + 0.001 * i)
        test.append(_row(f"s{i}", f"2023-07-{(1 + i) % 28 + 1:02d}", "W3",
                         {"f_ret_5d": fret,
                          "f_downside_prob": 0.8 if low else 0.2,
                          "instrument": "A:EQ"},
                         bool(i % 2)))
    return train, valid, test


def test_miner_discovers_planted_condition_train_valid_only():
    train, valid, test = _planted_split()
    res = CM.mine(train, valid, test, target="adverse_mae")
    assert res["status"] == "COMPLETE"
    assert res["candidates"], "planted condition missed"
    top = res["candidates"][0]
    assert any(any("f_ret_5d=low" in c for c in cand["condition"])
               for cand in res["candidates"])
    assert top["train"]["n"] >= CM.MIN_TRAIN_N
    assert top["test"]["rate"] is not None  # reported, not selected on


def test_test_mutation_cannot_change_discovery():
    train, valid, test = _planted_split()
    before = CM.mine(train, valid, test, target="adverse_mae")
    for r in test:  # scramble TEST outcomes entirely
        r["outcome"] = not r["outcome"]
    after = CM.mine(train, valid, test, target="adverse_mae")
    assert [c["condition"] for c in before["candidates"]] == [
        c["condition"] for c in after["candidates"]]
    assert [c["train"] for c in before["candidates"]] == [
        c["train"] for c in after["candidates"]]


def test_miner_null_when_no_signal():
    rows = [_row(f"d{i}", f"2023-05-{10 + (i % 20):02d}", "W1",
                 {"f_ret_5d": 0.01 * (i % 5),
                  "f_downside_prob": 0.5, "instrument": "A:EQ"},
                 bool(i % 2)) for i in range(30)]
    res = CM.mine(rows, rows, rows, target="adverse_mae")
    assert res["status"] == "COMPLETE"
    assert res["candidates"] == []


def test_diagnostic_join_provenance_tags():
    v1 = [{"keys": {"decision_id": "d", "experiment_id": "W",
                    "decision_timestamp": "2023-05-15"},
           "features": {"instrument": "A:EQ"},
           "outcomes": {"adverse_mae": True}}]
    v2 = [{"keys": {"decision_id": "d"},
           "features": {"nifty_return_5d": 0.01, "vix_change_5d": 0.02,
                        "instrument_return_5d": 0.03, "drawdown": 0.0}}]
    table = FD.build_diagnostic_table(
        v1, v2, {"d": {"f_ret_5d": -0.01}}, target="adverse_mae")
    row = table["rows"][0]
    assert row["feature_provenance"]["f_ret_5d"] == "MODEL_DERIVED"
    assert row["feature_provenance"]["instrument"] == "OBSERVED"
    assert row["outcome_provenance"] == "EVALUATOR_ONLY"
    assert "adverse_mae" not in row["features"]
    assert "mae" not in row["features"]


def test_hypothesis_roundtrip_and_candidate_only():
    train, valid, test = _planted_split()
    res = CM.mine(train, valid, test, target="adverse_mae")
    cand = res["candidates"][0]
    HB.set_band_cache(res["spec"])
    dh = HB.from_condition(
        cand, train, ["W1", "W2"], {"model_name": "stub"},
        forecast_fingerprint="ffp", information_set_fingerprint="isfp",
        target="adverse_mae", hypothesis_id="H1")
    assert dh.status == CANDIDATE
    assert DiagnosticHypothesis.from_dict(dh.to_dict()) == dh
    fh = HB.to_failure_hypothesis(
        dh, "t0", "W1", "2023-05-10", observed_target=True)
    assert isinstance(fh, FailureHypothesis)
    assert "BUY" not in fh.to_dict()["top_contributing_features"]
    bad = dh.to_dict()
    bad["status"] = "VALIDATED"
    with pytest.raises(ValueError):
        DiagnosticHypothesis.from_dict(bad)


def test_validation_accepts_and_rejects_without_admission():
    good = {"hypothesis_id": "H", "target": "adverse_mae",
            "condition": ["f_ret_5d=low"], "mechanism": "elevated rate noted",
            "observed_adverse_rate": 0.7, "baseline_adverse_rate": 0.4,
            "effect_delta": 0.3, "temporal_support": [("train", "n=20")],
            "sample_count": 20, "model_metadata": [],
            "feature_provenance": [("f_ret_5d", "MODEL_DERIVED")],
            "information_set_fingerprint": "x",
            "provenance_class": "INFERRED", "status": "CANDIDATE"}
    v = validate_candidate(good)
    assert v["verdict"] == "ACCEPT_FOR_ADMISSION_REVIEW"
    assert v["admission"].startswith("NOT_PERFORMED")
    bad = dict(good, sample_count=3)
    assert validate_candidate(bad)["verdict"] == "REJECT"


def test_ml_layer_touches_no_memory_or_oracle():
    import ast
    root = os.path.join(os.path.dirname(__file__), "..", "..",
                        "evaluation", "ml")
    hits = []
    for dirpath, _, files in os.walk(root):
        if "__pycache__" in dirpath:
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            tree = ast.parse(
                open(os.path.join(dirpath, f)).read())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    for token in ("memory", "MemoryStore", "oracle",
                                  "diagnostics.repair"):
                        if token.lower() in node.module.lower():
                            hits.append((f, f"import-from {node.module}"))
                    for a in node.names:
                        if a.name in ("MemoryStore", "OraclePacket",
                                      "TargetObservation"):
                            hits.append((f, f"import {a.name}"))
                elif isinstance(node, ast.Import):
                    for a in node.names:
                        if "MemoryStore" in a.name:
                            hits.append((f, f"import {a.name}"))
                elif isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Attribute) and func.attr in (
                            "adapt", "admit", "adjudicate"):
                        hits.append((f, f"call .{func.attr}()"))
    assert hits == [], f"boundary violation: {hits}"
