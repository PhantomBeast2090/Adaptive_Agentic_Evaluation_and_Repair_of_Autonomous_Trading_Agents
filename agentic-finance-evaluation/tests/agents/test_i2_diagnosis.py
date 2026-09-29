"""I2 diagnosis Tier-1 tests: shim equivalence (results identical with and
without the conditions cache), split mapping over I2 attribution ids.
Fast synthetic tests only; no outcome data.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from evaluation.ml.diagnosis import conditional_miner as CM  # noqa: E402


def _synthetic(n=120, seed=7):
    rng = random.Random(seed)
    cols = tuple(f"f{i}" for i in range(12))
    rows = []
    for i in range(n):
        rows.append({
            "keys": {"decision_id": f"d{i}",
                     "decision_timestamp": "2020-01-01",
                     "experiment_id": "probe"},
            "features": {c: rng.random() for c in cols},
            "outcome": rng.random() < 0.5})
    return rows, cols


def test_shim_equivalence():
    from scripts.run_i2_diagnosis import install_conditions_cache
    rows, cols = _synthetic()
    train, valid, test = rows[:60], rows[60:90], rows[90:]
    plain = CM.mine(train, valid, test, target="probe",
                    numeric_columns=cols,
                    categorical_columns=("instrument",))
    orig, cache = install_conditions_cache()
    try:
        assert len(cache) == 0
        fast = CM.mine(train, valid, test, target="probe",
                       numeric_columns=cols,
                       categorical_columns=("instrument",))
        assert len(cache) > 0  # cache actually engaged
    finally:
        CM._conditions_flat = orig
    assert fast["n_universe"] == plain["n_universe"]
    assert [c["condition"] for c in fast["candidates"]] == \
        [c["condition"] for c in plain["candidates"]]
    for a, b in zip(fast["candidates"], plain["candidates"]):
        assert a["train"] == b["train"]
        assert a["valid"] == b["valid"]
        assert a["test"] == b["test"]


def test_transfer_matches_miner_semantics():
    # Categorical action= clauses must match (HB._matches float-casts them
    # to False); band edges are inclusive in the miner. Build a tiny spec
    # with fit_bands and verify transfer counts equal CM._rate counts.
    from scripts.run_i2_diagnosis import transfer
    rows = []
    for i in range(40):
        rows.append({
            "keys": {"decision_id": f"t{i}",
                     "decision_timestamp": "2020-01-01",
                     "experiment_id": f"I2-{'W1' if i < 20 else 'W2'}-C0"},
            "features": {"x": float(i), "action": "SELL" if i % 2 else "BUY",
                         "instrument": "A"},
            "outcome": bool(i % 2)})
    spec = CM.fit_bands(rows, ("x",), ("action", "instrument"))
    cand = {"condition": ["action=SELL"]}
    got = transfer(rows, cand, spec)
    for w, n_exp in (("W1", 10), ("W2", 10)):
        assert got[w]["matched_n"] == n_exp, (w, got[w])
    assert got["transfer_pass"] is True
