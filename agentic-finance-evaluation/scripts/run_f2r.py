"""F2R rerun: existing F2 protocol against the frozen support split.

Split (docs/F2R_SPLIT_SPEC.md, fingerprint aba2ade5…):
  TRAIN = F1R-B (all) + F1R-A ts < 2020-02-15
  VALID = F1R-A 2020-02-15..2020-03-10 (n=6, weak by construction)
  TEST  = F1R-A ts > 2020-03-10 (SELL-only regime transition)
Targets, R1 schema, miner thresholds, permutation protocol unchanged.
Persist under data/frozen_traces/_f2r/. Nothing writes to MemoryStore.
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
TRAIN_END = "2020-02-15"
VALID_END = "2020-03-10"

NUMERICS = tuple(NUMERIC_FEATURES_V2) + tuple(S3.SEQ_FEATURES)
CATEGORICALS = ("instrument", "action") + tuple(CATEGORICAL_FEATURES_V2)


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
        bounds[os.path.basename(d.rstrip("/"))] = {
            "start": spec["grid_start"], "end": spec["grid_end"]}
    return bounds


def split(rows):
    out = {"train": [], "valid": [], "test": []}
    for r in rows:
        wid = r["keys"]["experiment_id"]
        ts = r["keys"]["decision_timestamp"]
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


def support_by(rows):
    from collections import Counter
    return {"n": len(rows),
            "actions": dict(Counter(
                str(r["features"].get("action")) for r in rows)),
            "instruments": dict(Counter(
                str(r["features"].get("instrument")) for r in rows))}


def run_mine(train, valid, test, target):
    return CM.mine(train, valid, test, target=target,
                   numeric_columns=NUMERICS,
                   categorical_columns=CATEGORICALS)


def falsify(train, valid, test, target, seed=PERMUTATION_SEED):
    base = [r["outcome"] for r in train]
    rng = random.Random(seed)
    idx = list(range(len(base)))
    rng.shuffle(idx)
    if all(i == j for i, j in enumerate(idx)) and len(idx) > 1:
        idx[0], idx[1] = idx[1], idx[0]
    pt = copy.deepcopy(train)
    for r, j in zip(pt, idx):
        r["outcome"] = base[j]
    perm = run_mine(pt, valid, test, target)
    return {"label_permutation": {
        "seed": seed, "labels_changed": True,
        "n_candidates": len(perm["candidates"]),
        "top_train_delta": (perm["candidates"][0]["train"]["delta"]
                            if perm["candidates"] else None),
        "universe": perm["n_universe"]}}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run F2R support rerun")
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
    v1_by = {r["keys"]["decision_id"]: r for r in v1["rows"]}
    srows = {r["keys"]["decision_id"]: r for r in seq["rows"]}
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

    import evaluation.ml.persistence as P
    results = {}
    for target in ("adverse_mae", "adverse_forward_3d"):
        rows = [{"keys": r["keys"], "features": r["features"],
                 "outcome": r["outcomes"].get(target)} for r in r1_rows]
        splits = split(rows)
        lab = {k: sum(1 for r in v if r["outcome"] is not None)
               for k, v in splits.items()}
        rates = {k: (sum(1 for r in v if r["outcome"]) / lab[k]
                     if lab[k] else None) for k, v in splits.items()}
        sup = {k: support_by([r for r in v if r["outcome"] is not None])
               for k, v in splits.items()}
        mined = run_mine(splits["train"], splits["valid"], splits["test"],
                         target)
        fals = falsify(splits["train"], splits["valid"], splits["test"],
                       target)
        HB.set_band_cache(mined["spec"])
        info_fp = fingerprint_artefacts(
            {"r1_ids": sorted(r["keys"]["decision_id"] for r in r1_rows)})
        hyps, vals = [], []
        for j, cand in enumerate(mined["candidates"]):
            dh = HB.from_condition(
                cand, splits["train"],
                ["F2R-TRAIN", "F2R-VALID", "F2R-TEST"],
                {"model_name": "conditional-miner-f2r"}, info_fp,
                info_fp, target, f"{args.experiment_id}-{target}-H{j + 1}")
            hyps.append(dh.to_dict())
            vals.append(validate_candidate(dh.to_dict()))
        results[target] = {
            "labelled": lab, "rates": rates, "support": sup,
            "universe": mined["n_universe"],
            "candidates": mined["candidates"],
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
                      "split_spec_sha256": sha256_of_file(os.path.join(
                          base, "data", "frozen_traces", "_f2r",
                          "split_spec.json")),
                      "splits": {"train": "F1R-B + F1R-A<2020-02-15",
                                 "valid": "F1R-A 2020-02-15..2020-03-10",
                                 "test": "F1R-A>2020-03-10"},
                      "targets": ["adverse_mae", "adverse_forward_3d"],
                      "seed": PERMUTATION_SEED},
           "results": results}
    sha = code_sha(base)
    prov = {"code_sha": sha,
            "data_shas": {d: sha256_of_file(os.path.join(
                base, d, "decision_table.csv")) for d in F1_DIRS},
            "device": "cpu", "seed": PERMUTATION_SEED}
    out = P.save_foundation(base, args.experiment_id, art, prov,
                            {"note": "F2R support rerun"},
                            args.overwrite, subdir=P.F2R_SUBDIR)
    print(f"persisted -> {out}")
    man = json.load(open(os.path.join(out, "manifest.json")))
    print(f"fingerprint: {man['fingerprint']}")


if __name__ == "__main__":
    main()
