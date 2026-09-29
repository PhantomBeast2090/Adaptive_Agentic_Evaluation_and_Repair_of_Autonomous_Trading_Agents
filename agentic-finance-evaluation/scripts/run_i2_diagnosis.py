"""I2 diagnosis: attribution (I2f) + frozen conditional mining (I2g) on the
frozen K1 winner (18 cells x W1/W2 = 36 branches).

Stage A (--stage attribution): frozen DecisionAttributionEngine
(CachedAttributionEngine shim from run_f1, byte-identical semantics) over
each K1 branch trace; persists I2-W*-C* attribution experiments.
Stage B (--stage mine): V1+V2+sequence R1 merge (run_f2 pattern), I2-third
splits, frozen conditional miner (N>=15/delta>=0.02/top-5), label
permutation (seed 20260926), hypothesis building + validation, and
cross-window (W1 vs W2) transfer check. Persists under _ml_i2/.

No MemoryStore writes; no repair in this script. STOP verdicts:
TEST labelled == 0 -> cannot confirm (I2-NULL path).
"""

from __future__ import annotations

import argparse
import copy
import datetime as _dt
import json
import os
import random
import sys

sys.path.insert(0, ".")

import yaml

from environment.indian.clock import build_master_grid, load_default_resolver
from evaluation.attribution import features_seq as S3
from evaluation.attribution import features_v2 as F2F
from evaluation.attribution.features import build_ml_dataset
from evaluation.attribution.features_v2 import (
    CATEGORICAL_FEATURES_V2, NUMERIC_FEATURES_V2,
)
from evaluation.attribution.persistence import save_experiment
from evaluation.ml.diagnosis import conditional_miner as CM
from evaluation.ml.diagnosis import hypothesis_builder as HB
from evaluation.ml.validation.ml_validation import validate_candidate
from scripts.run_f1 import CachedAttributionEngine
from scripts.run_i2 import load_spec as load_i2_spec

BASE_POLICY_CFG = "configs/choice_agent/i2_grid.yaml"
I1_EXP = "I1-20260928"
I2_EXP = "I2-20260928"
I1_IDS = ("C0", "C1", "C2", "C3", "C4", "C5")
PERMUTATION_SEED = 20260926

TAXONOMY_HINTS = {
    "F-ACC": ("exposure", "drawdown", "exec_freq", "buy_count",
              "persistence"),
    "F-CONC": ("instrument", "holdings", "dist_"),
    "F-VOL": ("vix_",),
    "F-CASH": ("cash", "cost"),
}

MANIFEST_PATHS = [
    "configs/indian_environment.yaml",
    "configs/choice_agent/i2_grid.yaml",
    "agents/choice/policy.py",
    "agents/choice/multi_asset.py",
    "data/processed/india/calendars/historical_calendar.csv",
    "data/processed/india/equities/nse_equity_daily.csv",
]


def k1_branches(base_dir: str) -> list:
    spec = load_i2_spec(base_dir)
    out = []
    for window in ("W1", "W2"):
        for cell in spec["candidates"]["K1"]["cells"]:
            if cell in I1_IDS:
                src = os.path.join(base_dir, "data", "frozen_traces",
                                   "_i1", I1_EXP, window, cell)
            else:
                src = os.path.join(base_dir, "data", "frozen_traces",
                                   "_i2", I2_EXP, window, cell)
            out.append((window, cell, src, f"I2-{window}-{cell}"))
    return out


def run_attribution(base_dir: str, overwrite: bool = False) -> None:
    for window, cell, src, exp_id in k1_branches(base_dir):
        with open(os.path.join(src, "baseline_result.json")) as h:
            result_dict = json.load(h)
        with open(os.path.join(src, "baseline_config.json")) as h:
            config_dict = json.load(h)
        with open(os.path.join(src, "environment_spec.json")) as h:
            env_spec = json.load(h)
        grid = [d.isoformat() for d in build_master_grid(
            load_default_resolver(base_dir),
            _dt.date.fromisoformat(env_spec["grid_start"]),
            _dt.date.fromisoformat(env_spec["grid_end"]))]
        engine = CachedAttributionEngine(base_dir=base_dir)
        attribution = engine.attribute_trajectory(
            decision_records=result_dict["decision_records"],
            episode_id=exp_id + "-ep1", arm="A",
            trajectory_fingerprint=result_dict["result_fingerprint"],
            run_id=exp_id + "-run-001", experiment_id=exp_id,
            experiment_grid=grid, context_descriptor="C0-empty-store")
        extra = {"attribution_fingerprint": attribution.fingerprint(),
                 "arm": "A", "source_window": window,
                 "source_cell": cell, "candidate": "K1"}
        out = save_experiment(
            base_dir=base_dir, experiment_id=exp_id,
            config_dict=config_dict, environment_spec=env_spec,
            baseline_result_dict=result_dict,
            attribution_dict=attribution.to_dict(),
            manifest_paths=MANIFEST_PATHS, extra=extra,
            overwrite=overwrite)
        n = len(attribution.to_dict().get("attributed_decisions", []))
        print(f"I2f {exp_id}: {n} rows -> {out}")


def split_rows(rows, spec: dict):
    out = {"train": [], "valid": [], "test": []}
    thirds = spec["splits"]
    train_ranges = [thirds[t] for t in thirds["TRAIN"]]
    valid_ranges = [thirds[t] for t in thirds["VALID"]]
    test_ranges = [thirds[t] for t in thirds[thirds_key(spec)]]

    def in_ranges(date, ranges):
        return any(r["start"] <= date <= r["end"] for r in ranges)
    for r in rows:
        ts = r["keys"]["decision_timestamp"]
        if in_ranges(ts, train_ranges):
            out["train"].append(r)
        elif in_ranges(ts, valid_ranges):
            out["valid"].append(r)
        elif in_ranges(ts, test_ranges):
            out["test"].append(r)
    for v in out.values():
        v.sort(key=lambda r: (r["keys"]["decision_timestamp"],
                              r["keys"]["decision_id"]))
    return out


def thirds_key(spec: dict) -> str:
    return spec["candidates"]["K1"]["test"]


def window_of(row) -> str:
    exp = row["keys"]["experiment_id"]
    return "W1" if "-W1-" in exp else "W2"


def taxonomy_of(condition):
    text = " ".join(condition)
    hits = [t for t, hints in TAXONOMY_HINTS.items()
            if any(h in text for h in hints)]
    return hits or ["UNMATCHED"]


def falsify(train, valid, test, numeric, categorical, target,
            seed=PERMUTATION_SEED):
    base = [r["outcome"] for r in train]
    rng = random.Random(seed)
    idx = list(range(len(base)))
    rng.shuffle(idx)
    if all(i == j for i, j in enumerate(idx)) and len(idx) > 1:
        idx[0], idx[1] = idx[1], idx[0]
    pt = copy.deepcopy(train)
    for r, j in zip(pt, idx):
        r["outcome"] = base[j]
    perm = CM.mine(pt, valid, test, target, numeric, categorical)
    return {"label_permutation": {
        "seed": seed, "labels_changed": True,
        "n_candidates": len(perm["candidates"]),
        "top_train_delta": (perm["candidates"][0]["train"]["delta"]
                            if perm["candidates"] else None)}}


def transfer(rows_labelled, candidate, spec):
    """Cross-window transfer: condition matched-rate vs baseline in W1, W2.

    Matching uses the frozen miner's own semantics (flat condition-set
    membership via CM._conditions_flat, cache-accelerated) so categorical
    clauses (e.g. action=SELL) and band edges behave exactly as in mining.
    """
    cond = set(candidate["condition"])
    out = {}
    for window in ("W1", "W2"):
        wrows = [r for r in rows_labelled if window_of(r) == window
                 and r["outcome"] is not None]
        matched = [r for r in wrows
                   if cond <= set(CM._conditions_flat(r, spec))]
        base_rate = (sum(1 for r in wrows if r["outcome"]) / len(wrows)
                     if wrows else None)
        match_rate = (sum(1 for r in matched if r["outcome"]) / len(matched)
                      if matched else None)
        out[window] = {"n": len(wrows), "matched_n": len(matched),
                       "baseline": base_rate, "matched_rate": match_rate}
    ok = all(out[w]["matched_n"] >= 5 and out[w]["matched_rate"] is not None
               and out[w]["baseline"] is not None
               and out[w]["matched_rate"] > out[w]["baseline"]
               for w in ("W1", "W2"))
    out["transfer_pass"] = bool(ok)
    return out


def install_conditions_cache():
    """Performance shim (F1 CachedAttributionEngine precedent): memoize the
    frozen miner's per-row condition expansion. The miner re-derives every
    row's ~1500 condition tuples once PER UNIVERSE CONDITION (~11k x); on
    I2-scale rows (1743 TRAIN) that is ~10^10 redundant tuple rebuilds in
    pure Python (~7h per mine call by timing probe). Memoization returns
    bit-identical outputs (pure function, keyed by decision_id + spec
    identity; permuted deepcopy rows share decision_ids AND features, so
    cache hits remain correct). Frozen miner file untouched; thresholds,
    logic, and results identical. Equivalence is proven by
    tests/agents/test_i2_diagnosis.py::test_shim_equivalence.
    """
    from evaluation.ml.diagnosis import conditional_miner as CM
    orig = CM._conditions_flat
    cache: dict = {}

    def memo(row, spec):
        key = (row["keys"]["decision_id"], id(spec))
        hit = cache.get(key)
        if hit is None:
            hit = orig(row, spec)
            cache[key] = hit
        return hit

    CM._conditions_flat = memo
    return orig, cache


def run_mine(base_dir: str, experiment_id: str,
             overwrite: bool = False) -> dict:
    install_conditions_cache()
    spec = load_i2_spec(base_dir)
    dirs = [f"data/frozen_traces/I2-{w}-{c}"
            for w in ("W1", "W2") for c in spec["candidates"]["K1"]["cells"]]
    v1 = build_ml_dataset(dirs, base_dir=base_dir,
                          grid_bounds=_grid_bounds(base_dir, dirs))
    v2 = F2F.build_ml_dataset_v2(dirs, base_dir=base_dir)
    seq = S3.build_sequence_features(dirs, base_dir=base_dir)
    print(f"V1={v1['manifest']['n_rows']} V2={v2['manifest']['n_rows']} "
          f"SEQ={seq['manifest']['n_rows']}")
    srows = {r["keys"]["decision_id"]: r for r in seq["rows"]}
    v1_by = {r["keys"]["decision_id"]: r for r in v1["rows"]}
    r1_rows = []
    for r in v2["rows"]:
        did = r["keys"]["decision_id"]
        merged = dict(r["features"])
        merged.update(srows[did]["features"])
        v1f = v1_by.get(did, {}).get("features", {})
        for field in ("instrument", "action"):
            if field in v1f:
                merged[field] = v1f[field]
        r1_rows.append({"keys": dict(r["keys"]), "features": merged,
                        "outcomes": dict(r["outcomes"])})
    numeric = tuple(NUMERIC_FEATURES_V2) + tuple(S3.SEQ_FEATURES)
    categorical = ("instrument", "action") + tuple(CATEGORICAL_FEATURES_V2)
    results = {}
    for target in ("adverse_mae", "adverse_forward_3d"):
        rows = [{"keys": r["keys"], "features": r["features"],
                 "outcome": r["outcomes"].get(target)} for r in r1_rows]
        splits = split_rows(rows, spec)
        lab = {k: sum(1 for r in v if r["outcome"] is not None)
               for k, v in splits.items()}
        rates = {k: (sum(1 for r in v if r["outcome"]) / lab[k]
                     if lab[k] else None) for k, v in splits.items()}
        print(f"{target}: labelled={lab} rates="
              + str({k: round(v, 3) if v is not None else None
                     for k, v in rates.items()}))
        if lab["test"] == 0:
            results[target] = {"labelled": lab, "rates": rates,
                               "verdict": "UNTESTABLE-TEST-EMPTY"}
            continue
        mined = CM.mine(splits["train"], splits["valid"], splits["test"],
                        target=target, numeric_columns=numeric,
                        categorical_columns=categorical)
        fals = falsify(splits["train"], splits["valid"], splits["test"],
                       numeric, categorical, target)
        HB.set_band_cache(mined["spec"])
        labelled_all = [r for r in rows if r["outcome"] is not None]
        cands = []
        for j, cand in enumerate(mined["candidates"]):
            dh = HB.from_condition(
                cand, splits["train"],
                ["I2-TRAIN", "I2-VALID", "I2-TEST"],
                {"model_name": "conditional-miner-i2",
                 "taxonomy": taxonomy_of(cand["condition"])},
                "i2-info", "i2-info", target,
                f"{experiment_id}-{target}-H{j + 1}")
            val = validate_candidate(dh.to_dict())
            cands.append({
                "condition": cand["condition"],
                "taxonomy": taxonomy_of(cand["condition"]),
                "train": cand["train"],
                "valid": cand["valid"],
                "test": cand["test"],
                "transfer": transfer(labelled_all, cand, mined["spec"]),
                "hypothesis": dh.to_dict(),
                "validation": val})
        top_delta = (mined["candidates"][0]["train"]["delta"]
                     if mined["candidates"] else None)
        perm_n = fals["label_permutation"]["n_candidates"]
        perm_delta = fals["label_permutation"]["top_train_delta"]
        real_beats_perm = (
            len(mined["candidates"]) > perm_n
            and (top_delta or 0) > (perm_delta or 0))
        results[target] = {
            "labelled": lab, "rates": rates,
            "universe": mined["n_universe"],
            "n_candidates": len(mined["candidates"]),
            "top_train_delta": top_delta,
            "permutation": fals["label_permutation"],
            "real_beats_permutation": bool(real_beats_perm),
            "candidates": cands}
        print(f"{target}: universe={mined['n_universe']} "
              f"candidates={len(mined['candidates'])} perm={perm_n} "
              f"real>perm={bool(real_beats_perm)}")
    out_dir = os.path.join(base_dir, "data", "frozen_traces", "_ml_i2",
                           experiment_id)
    os.makedirs(out_dir, exist_ok=True)
    if os.path.exists(os.path.join(out_dir, "results.json")) \
            and not overwrite:
        raise FileExistsError(f"refusing to overwrite {out_dir}")
    payload = {"experiment_id": experiment_id, "candidate": "K1",
               "targets": ["adverse_mae", "adverse_forward_3d"],
               "results": results}
    with open(os.path.join(out_dir, "results.json"), "w",
              encoding="utf-8") as h:
        json.dump(payload, h, sort_keys=True, separators=(",", ":"))
        h.write("\n")
    with open(os.path.join(out_dir, "spec.json"), "w",
              encoding="utf-8") as h:
        json.dump(load_i2_spec(base_dir), h, sort_keys=True,
                  separators=(",", ":"))
        h.write("\n")
    print(f"persisted -> {out_dir}")
    return results


def _grid_bounds(base_dir: str, dirs: list) -> dict:
    bounds = {}
    for d in dirs:
        with open(os.path.join(base_dir, d, "environment_spec.json")) as h:
            spec = json.load(h)
        bounds[os.path.basename(d)] = {"start": spec["grid_start"],
                                       "end": spec["grid_end"]}
    return bounds


def main() -> None:
    parser = argparse.ArgumentParser(description="I2 diagnosis")
    parser.add_argument("--stage", choices=["attribution", "mine"],
                        required=True)
    parser.add_argument("--experiment-id", default="I2-20260928")
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.stage == "attribution":
        run_attribution(args.base_dir, args.overwrite)
    else:
        run_mine(args.base_dir, args.experiment_id, args.overwrite)


if __name__ == "__main__":
    main()
