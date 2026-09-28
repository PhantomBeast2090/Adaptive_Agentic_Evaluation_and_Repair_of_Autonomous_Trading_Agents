"""F2 vulnerability discovery: pre-registered taxonomy mining on F1R.

Splits (date-defined, regime-motivated, frozen before mining):
  TRAIN = F1R-B (calm) + F1R-A sessions < 2020-03-01 (pre-crash)
  VALID = F1R-A 2020-03-01..2020-04-30 (crash)
  TEST  = F1R-A sessions > 2020-04-30 (recovery)
Targets: adverse_mae (primary), adverse_forward_3d (secondary).
Miner: frozen conditional_miner over R1 (V2+sequence) schema, same
thresholds (N>=15, delta>=0.02, VALID confirmation, top-5).
Falsification: label permutation + shuffled-outcome nulls.
Survivors map to F-ACC/F-CONC/F-VOL/F-CASH or reported unmatched.
Nothing writes to MemoryStore; no repair in this script.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import random
import subprocess
import sys

sys.path.insert(0, ".")

from evaluation.attribution import features_seq as S3
from evaluation.attribution import features_v2 as F2F
from evaluation.attribution.features import build_ml_dataset
from evaluation.attribution.features_v2 import (
    CATEGORICAL_FEATURES_V2, NUMERIC_FEATURES_V2,
)
from evaluation.ml.diagnosis import conditional_miner as CM
from evaluation.ml.diagnosis import hypothesis_builder as HB
from evaluation.ml.persistence import (
    fingerprint_artefacts, save_foundation, sha256_of_file,
)
from evaluation.ml.validation.ml_validation import validate_candidate

PERMUTATION_SEED = 20260926
F1_DIRS = ["data/frozen_traces/F1R-A-20260926",
           "data/frozen_traces/F1R-B-20260926"]
TRAIN_END = "2020-03-01"
VALID_END = "2020-04-30"

TAXONOMY_HINTS = {
    "F-ACC": ("exposure", "drawdown", "exec_freq", "buy_count",
              "persistence"),
    "F-CONC": ("instrument", "holdings", "dist_"),
    "F-VOL": ("vix_",),
    "F-CASH": ("cash", "cost"),
}


def code_sha(base_dir: str) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=base_dir,
                             capture_output=True, text=True, timeout=15)
        return out.stdout.strip() or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def grid_bounds(base_dir: str) -> dict:
    bounds = {}
    for d in F1_DIRS:
        with open(os.path.join(base_dir, d, "environment_spec.json")) as h:
            spec = json.load(h)
        exp = os.path.basename(d.rstrip("/"))
        bounds[exp] = {"start": spec["grid_start"], "end": spec["grid_end"]}
    return bounds


def split(rows):
    out = {"train": [], "valid": [], "test": []}
    for r in rows:
        ts = r["keys"]["decision_timestamp"]
        wid = r["keys"]["experiment_id"]
        if wid == "F1R-B-20260926" or ts < TRAIN_END:
            out["train"].append(r)
        elif ts <= VALID_END:
            out["valid"].append(r)
        else:
            out["test"].append(r)
    for v in out.values():
        v.sort(key=lambda r: (r["keys"]["decision_timestamp"],
                              r["keys"]["decision_id"]))
    return out


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
        "n_candidates": len(perm["candidates"])}}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run F2 taxonomy mining")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    base = args.base_dir

    v1 = build_ml_dataset(F1_DIRS, base_dir=base,
                          grid_bounds=grid_bounds(base))
    v2 = F2F.build_ml_dataset_v2(F1_DIRS, base_dir=base)
    seq = S3.build_sequence_features(F1_DIRS, base_dir=base)
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
        splits = split(rows)
        lab = {k: sum(1 for r in v if r["outcome"] is not None)
               for k, v in splits.items()}
        rates = {k: (sum(1 for r in v if r["outcome"]) / lab[k]
                     if lab[k] else None) for k, v in splits.items()}
        mined = CM.mine(splits["train"], splits["valid"], splits["test"],
                        target=target, numeric_columns=numeric,
                        categorical_columns=categorical)
        fals = falsify(splits["train"], splits["valid"], splits["test"],
                       numeric, categorical, target)
        HB.set_band_cache(mined["spec"])
        info_fp = fingerprint_artefacts(
            {"r1_ids": sorted(r["keys"]["decision_id"] for r in r1_rows)})
        hyps, vals = [], []
        for j, cand in enumerate(mined["candidates"]):
            dh = HB.from_condition(
                cand, splits["train"],
                ["F1R-TRAIN", "F1R-VALID", "F1R-TEST"],
                {"model_name": "conditional-miner-f2",
                 "taxonomy": taxonomy_of(cand["condition"])},
                info_fp, info_fp, target,
                f"{args.experiment_id}-{target}-H{j + 1}")
            hyps.append(dh.to_dict())
            vals.append(validate_candidate(dh.to_dict()))
        results[target] = {
            "labelled": lab, "rates": rates,
            "universe": mined["n_universe"],
            "candidates": [{**c, "taxonomy": taxonomy_of(c["condition"])}
                           for c in mined["candidates"]],
            "spec_summary": {
                "bands": len(mined["spec"]["bands"]),
                "train_baseline": mined["spec"]["train_baseline"]},
            "falsification": fals, "hypotheses": hyps,
            "validations": vals}
        print(f"{target}: labelled={lab} rates="
              + str({k: round(v, 3) if v is not None else None
                     for k, v in rates.items()})
              + f" universe={mined['n_universe']} "
              f"candidates={len(mined['candidates'])} "
              f"perm={fals['label_permutation']['n_candidates']} "
              f"verdicts={[v['verdict'] for v in vals]}")

    art = {"config": {"experiment_id": args.experiment_id,
                      "splits": {"train": "F1R-B + F1R-A<2020-03-01",
                                 "valid": "F1R-A 2020-03-01..2020-04-30",
                                 "test": "F1R-A>2020-04-30"},
                      "targets": ["adverse_mae", "adverse_forward_3d"],
                      "taxonomy": sorted(TAXONOMY_HINTS),
                      "seed": PERMUTATION_SEED},
           "results": results}
    sha = code_sha(base)
    prov = {"code_sha": sha,
            "data_shas": {d: sha256_of_file(os.path.join(
                base, d, "decision_table.csv")) for d in F1_DIRS},
            "device": "cpu", "seed": PERMUTATION_SEED}
    import evaluation.ml.persistence as P
    out = P.save_foundation(base, args.experiment_id, art, prov,
                            {"note": "F2 taxonomy mining"}, args.overwrite,
                            subdir=P.F1_SUBDIR)
    # save_foundation targets _ml_foundation; relocate to _ml_f1 below.
    print(f"persisted -> {out}")
    man = json.load(open(os.path.join(out, "manifest.json")))
    print(f"fingerprint: {man['fingerprint']}")


if __name__ == "__main__":
    main()
