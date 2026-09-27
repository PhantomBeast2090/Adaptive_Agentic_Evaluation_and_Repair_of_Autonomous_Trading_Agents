"""P2 counterfactual-regret miner: frozen E5A-1/2/3 experiment.

Pipeline: frozen R1 rows -> regret view (BUY-vs-HOLD, band 0.01) ->
TRAIN-band miner over R1 decision-time features -> VALID confirmation
-> TEST report -> hypothesis objects -> validation review ->
_ml_sequence persistence. Falsification: label permutation +
shuffled-regret nulls (seed 20260926). Nothing writes to MemoryStore;
the agent, gate, and frozen evidence are untouched.
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

from evaluation.attribution import regret as RG
from evaluation.attribution.features_seq import SEQ_FEATURES
from evaluation.attribution.features_v2 import (
    CATEGORICAL_FEATURES_V2, NUMERIC_FEATURES_V2,
)
from evaluation.ml.diagnosis import conditional_miner as CM
from evaluation.ml.diagnosis import hypothesis_builder as HB
from evaluation.ml.experiment import (
    TEST_WINDOW, TRAIN_WINDOW, VALID_WINDOW,
)
from evaluation.ml.persistence import (
    SEQUENCE_SUBDIR, fingerprint_artefacts, save_foundation,
    sha256_of_file,
)
from evaluation.ml.validation.ml_validation import validate_candidate

PERMUTATION_SEED = 20260926
V1_DATASET = "data/frozen_traces/_ml/e5a_combined_v1.json"

REGRET_NUMERICS = tuple(NUMERIC_FEATURES_V2) + tuple(SEQ_FEATURES)
REGRET_CATEGORICALS = ("instrument", "action") + tuple(
    CATEGORICAL_FEATURES_V2)


def code_sha(base_dir: str) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=base_dir,
                             capture_output=True, text=True, timeout=15)
        return out.stdout.strip() or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def to_miner_rows(regret_rows):
    out = []
    for r in regret_rows:
        out.append({"keys": dict(r["keys"]), "features": dict(r["features"]),
                    "outcome": r["regret_adverse"],
                    "regret_3d": r["regret_3d"]})
    return out


def split(rows):
    out = {"train": [], "valid": [], "test": []}
    for r in rows:
        wid = r["keys"]["experiment_id"]
        if wid == TRAIN_WINDOW:
            out["train"].append(r)
        elif wid == VALID_WINDOW:
            out["valid"].append(r)
        elif wid == TEST_WINDOW:
            out["test"].append(r)
    for v in out.values():
        v.sort(key=lambda r: (r["keys"]["decision_timestamp"],
                              r["keys"]["decision_id"]))
    return out


def run_mine(train, valid, test):
    return CM.mine(train, valid, test, target="regret_3d",
                   numeric_columns=REGRET_NUMERICS,
                   categorical_columns=REGRET_CATEGORICALS)


def falsify(train, valid, test, seed=PERMUTATION_SEED):
    """Label-permutation + shuffled-regret nulls (TRAIN only)."""
    base_labels = [r["outcome"] for r in train]
    # (a) boolean label permutation
    rng = random.Random(seed)
    idx = list(range(len(base_labels)))
    rng.shuffle(idx)
    if all(i == j for i, j in enumerate(idx)) and len(idx) > 1:
        idx[0], idx[1] = idx[1], idx[0]
    perm_train = copy.deepcopy(train)
    for r, j in zip(perm_train, idx):
        r["outcome"] = base_labels[j]
    perm_res = run_mine(perm_train, valid, test)
    # (b) shuffled continuous regret, frozen band re-applied
    vals = [r["regret_3d"] for r in train]
    rng2 = random.Random(seed + 1)
    idx2 = list(range(len(vals)))
    rng2.shuffle(idx2)
    shuf_train = copy.deepcopy(train)
    for r, j in zip(shuf_train, idx2):
        v = vals[j]
        r["regret_3d"] = v
        r["outcome"] = (v > RG.REGRET_BAND) if v is not None else None
    shuf_res = run_mine(shuf_train, valid, test)
    return {
        "label_permutation": {
            "seed": seed,
            "labels_changed": [r["outcome"] for r in perm_train]
                              != base_labels,
            "n_candidates": len(perm_res["candidates"]),
            "top_train_delta": (perm_res["candidates"][0]["train"]["delta"]
                                if perm_res["candidates"] else None),
            "universe": perm_res["n_universe"]},
        "shuffled_regret": {
            "seed": seed + 1,
            "n_candidates": len(shuf_res["candidates"]),
            "top_train_delta": (shuf_res["candidates"][0]["train"]["delta"]
                                if shuf_res["candidates"] else None),
            "universe": shuf_res["n_universe"]},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run P2 regret miner")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    base = args.base_dir

    r1 = RG.load_r1(base)
    with open(os.path.join(base, V1_DATASET)) as h:
        v1 = json.load(h)
    built = RG.build_regret_table(r1, v1)
    rows = to_miner_rows(built["rows"])
    splits = split(rows)
    labelled = {k: sum(1 for r in v if r["outcome"] is not None)
                for k, v in splits.items()}
    rates = {k: (sum(1 for r in v if r["outcome"]) / labelled[k]
                 if labelled[k] else None)
             for k, v in splits.items()}
    print(f"regret-labelled: {labelled}, rates: "
          + ", ".join(f"{k}={v:.3f}" if v is not None else f"{k}=None"
                      for k, v in rates.items()))

    mined = run_mine(splits["train"], splits["valid"], splits["test"])
    print(f"universe={mined['n_universe']}, "
          f"candidates={len(mined['candidates'])}")
    fals = falsify(splits["train"], splits["valid"], splits["test"])
    print(f"falsification: perm={fals['label_permutation']['n_candidates']}, "
          f"shuffled={fals['shuffled_regret']['n_candidates']}")

    HB.set_band_cache(mined["spec"])
    reg_fp = fingerprint_artefacts(
        {"regret_rows": [(r["keys"]["decision_id"], r["regret_3d"],
                          r["regret_adverse"]) for r in rows]})
    sha = code_sha(base)
    info_fp = fingerprint_artefacts({"built_manifest": built["manifest"]})
    hypotheses, validations = [], []
    for j, cand in enumerate(mined["candidates"]):
        dh = HB.from_condition(
            cand, splits["train"],
            [TRAIN_WINDOW, VALID_WINDOW, TEST_WINDOW],
            {"model_name": "conditional-miner-regret",
             "numeric_columns": len(REGRET_NUMERICS),
             "categorical_columns": list(REGRET_CATEGORICALS),
             "band": RG.REGRET_BAND},
            reg_fp, info_fp, "regret_3d",
            f"{args.experiment_id}-H{j + 1}")
        hypotheses.append(dh.to_dict())
        validations.append(validate_candidate(dh.to_dict()))
    print(f"hypotheses={len(hypotheses)}, "
          f"verdicts={[v['verdict'] for v in validations]}")

    diag_table = [
        {"decision_id": r["keys"]["decision_id"],
         "experiment_id": r["keys"]["experiment_id"],
         "features": r["features"],
         "regret_3d": r["regret_3d"],
         "regret_adverse": r["regret_adverse"]} for r in rows]
    art = {
        "config": {"experiment_id": args.experiment_id,
                   "target": "regret_3d",
                   "regret_band": RG.REGRET_BAND,
                   "regret_definition": built["manifest"][
                       "regret_definition"],
                   "cost_note": built["manifest"]["cost_note"],
                   "numeric_columns": list(REGRET_NUMERICS),
                   "categorical_columns": list(REGRET_CATEGORICALS),
                   "windows": {"train": TRAIN_WINDOW,
                               "valid": VALID_WINDOW,
                               "test": TEST_WINDOW},
                   "permutation_seed": PERMUTATION_SEED,
                   "labelled_counts": labelled,
                   "split_rates": rates},
        "diagnostic_table": diag_table,
        "mined_conditions": mined,
        "hypotheses": hypotheses,
        "validations": validations,
        "falsification": fals,
    }
    v3_path = os.path.join(
        base, "data", "frozen_traces", "_ml_sequence",
        "e5a_combined_v3.json")
    prov = {
        "code_sha": sha,
        "data_shas": {
            "e5a_combined_v3.json": sha256_of_file(v3_path),
            "e5a_combined_v1.json": sha256_of_file(
                os.path.join(base, V1_DATASET))},
        "regret_table_manifest": built["manifest"],
        "dependency_versions": {},
        "device": "cpu",
        "seed": PERMUTATION_SEED,
    }
    out = save_foundation(base, args.experiment_id, art, prov,
                          {"note": "P2 counterfactual-regret miner"},
                          args.overwrite)
    print(f"persisted -> {out}")
    man = json.load(open(os.path.join(out, "manifest.json")))
    print(f"fingerprint: {man['fingerprint']}")


if __name__ == "__main__":
    main()
