"""F1/F2 runner tests: shim equivalence (sampled), split logic."""

import sys

import pytest

sys.path.insert(0, "scripts")

from evaluation.attribution.engine import DecisionAttributionEngine


def test_cached_shim_matches_frozen_legs():
    run_f1 = pytest.importorskip("run_f1")
    frozen = DecisionAttributionEngine(base_dir=".")
    cached = run_f1.CachedAttributionEngine(base_dir=".")
    cases = [("nse_equity", "RELIANCE:EQ", "2023-05-16"),
             ("nse_equity", "TCS:EQ", "2023-06-29"),  # holiday gap
             ("nse_equity", "INFY:EQ", "2020-03-24"),  # crash
             ("nse_equity", "RELIANCE:EQ", "2020-04-29")]
    for asset, inst, sess in cases:
        assert cached._ohlc(asset, inst, sess) == frozen._ohlc(
            asset, inst, sess)


def test_f2_split_date_logic():
    run_f2 = pytest.importorskip("run_f2")
    rows = [
        {"keys": {"decision_id": "a", "experiment_id": "F1R-B-20260926",
                  "decision_timestamp": "2023-06-01"}},
        {"keys": {"decision_id": "b", "experiment_id": "F1R-A-20260926",
                  "decision_timestamp": "2020-02-01"}},
        {"keys": {"decision_id": "c", "experiment_id": "F1R-A-20260926",
                  "decision_timestamp": "2020-03-15"}},
        {"keys": {"decision_id": "d", "experiment_id": "F1R-A-20260926",
                  "decision_timestamp": "2020-05-01"}},
    ]
    out = run_f2.split(rows)
    assert [r["keys"]["decision_id"] for r in out["train"]] == ["b", "a"]
    assert [r["keys"]["decision_id"] for r in out["valid"]] == ["c"]
    assert [r["keys"]["decision_id"] for r in out["test"]] == ["d"]


def test_f1_id_namespace_guard():
    run_f1 = pytest.importorskip("run_f1")
    assert run_f1.F0_MAP["F0R-A-20260926"] == "F1R-A-20260926"
