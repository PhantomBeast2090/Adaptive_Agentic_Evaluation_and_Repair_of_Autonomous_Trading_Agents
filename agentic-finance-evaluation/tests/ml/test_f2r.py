"""F2R tests: split contract, thresholds frozen, determinism."""

import sys

import pytest

sys.path.insert(0, "scripts")


def test_split_boundaries_overlap_free_ordered():
    run_f2r = pytest.importorskip("run_f2r")
    rows = [
        {"keys": {"decision_id": "a", "experiment_id": "F1R-B-20260926",
                  "decision_timestamp": "2023-06-01"}},
        {"keys": {"decision_id": "b", "experiment_id": "F1R-A-20260926",
                  "decision_timestamp": "2020-01-10"}},
        {"keys": {"decision_id": "c", "experiment_id": "F1R-A-20260926",
                  "decision_timestamp": "2020-02-20"}},
        {"keys": {"decision_id": "d", "experiment_id": "F1R-A-20260926",
                  "decision_timestamp": "2020-04-01"}},
    ]
    out = run_f2r.split(rows)
    got = {k: [r["keys"]["decision_id"] for r in v]
           for k, v in out.items()}
    assert got == {"train": ["b", "a"], "valid": ["c"], "test": ["d"]}
    seen = [i for v in out.values() for r in v
            for i in [r["keys"]["decision_id"]]]
    assert sorted(seen) == ["a", "b", "c", "d"]
    stamps = {"train": "2020-02-15", "valid": "2020-03-10"}
    assert max(r["keys"]["decision_timestamp"] for r in out["train"]
               if r["keys"]["experiment_id"] == "F1R-A-20260926") < \
        stamps["train"]
    assert max(r["keys"]["decision_timestamp"] for r in out["valid"]) <= \
        stamps["valid"]
    assert min(r["keys"]["decision_timestamp"] for r in out["test"]) > \
        stamps["valid"]


def test_thresholds_byte_identical_to_miner():
    run_f2r = pytest.importorskip("run_f2r")
    from evaluation.ml.diagnosis import conditional_miner as CM
    assert CM.MIN_TRAIN_N == 15
    assert CM.MIN_TRAIN_DELTA == 0.02
    assert CM.MAX_CANDIDATES == 5
    assert run_f2r.PERMUTATION_SEED == 20260926
    assert run_f2r.TRAIN_END == "2020-02-15"
    assert run_f2r.VALID_END == "2020-03-10"


def test_split_spec_fingerprint_stable():
    import hashlib
    import os
    p = os.path.join(os.path.dirname(__file__), "..", "..",
                     "data", "frozen_traces", "_f2r", "split_spec.json")
    digest = hashlib.sha256(open(p, "rb").read()).hexdigest()
    assert digest == "aba2ade5401c80ed357d2df81fcab3dfd872f6c5cf14358d2eaea8d587ee595d"
