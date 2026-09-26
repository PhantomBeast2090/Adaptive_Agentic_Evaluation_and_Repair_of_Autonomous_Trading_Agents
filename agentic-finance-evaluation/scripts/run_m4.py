"""M4 sequence experiment: R0 (V2) vs R1 (V2+sequence) ablation.

Frozen protocol: TRAIN=E5A-1 / VALID=E5A-2 / TEST=E5A-3, targets
adverse_mae (primary) + adverse_forward_3d (secondary, separate),
Logistic + HistGradientBoosting with fixed configs, permutation seed
20260926, Brier primary. R0 reruns V2 in the same code path as R1 so
the comparison is exact. Nothing writes to MemoryStore; the agent and
validation machinery are untouched.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, ".")

from evaluation.attribution import features_seq as S3
from evaluation.attribution.features_v2 import (
    CATEGORICAL_FEATURES_V2, NUMERIC_FEATURES_V2,
    ZERO_FILL_FEATURES_V2,
)
from evaluation.ml.experiment import (
    PRIMARY_TARGET, SECONDARY_TARGET, run_cell,
)
from evaluation.ml.models.hist_gradient_boosting import HGBModel
from evaluation.ml.models.logistic import LogisticModel
from evaluation.ml.persistence import (
    SEQUENCE_SUBDIR, save_m2, sha256_of_file,
)

WINDOWS = [
    "data/frozen_traces/E5A-deterministic-attribution-20260926",
    "data/frozen_traces/E5A-window2-20260926",
    "data/frozen_traces/E5A-window3-20260926",
]
V2_DATASET = "data/frozen_traces/_ml/e5a_combined_v2.json"
R1_DATASET_OUT = "data/frozen_traces/_ml_sequence/e5a_combined_v3.json"


def code_sha(base_dir: str) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=base_dir,
                             capture_output=True, text=True, timeout=15)
        return out.stdout.strip() or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run M4 sequence ablation")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    base = args.base_dir

    with open(os.path.join(base, V2_DATASET)) as h:
        v2 = json.load(h)
    seq = S3.build_sequence_features(WINDOWS, base_dir=base)
    print(f"V2 rows: {v2['manifest']['n_rows']}, "
          f"V3 rows: {seq['manifest']['n_rows']}")
    srows = {r["keys"]["decision_id"]: r for r in seq["rows"]}
    r1_rows = []
    for r in v2["rows"]:
        did = r["keys"]["decision_id"]
        assert did in srows, f"sequence gap for {did}"
        merged = dict(r["features"])
        merged.update(srows[did]["features"])
        r1_rows.append({"keys": dict(r["keys"]), "features": merged,
                        "outcomes": dict(r["outcomes"])})
    r1 = {"rows": r1_rows, "manifest": {
        "n_rows": len(r1_rows),
        "r0_schema": list(v2["manifest"]["feature_schema"]),
        "r1_extra_schema": list(S3.SEQ_FEATURES),
        "v2_fingerprint_note": "R0 rows identical to frozen _ml dataset",
        "seq_missingness": seq["manifest"]["feature_missingness"],
        "builder": "scripts/run_m4.py:R1=V2+sequence merge on decision_id"}}

    out_path = os.path.join(base, R1_DATASET_OUT)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    if os.path.exists(out_path) and not args.overwrite:
        raise FileExistsError(f"refusing to overwrite {out_path}")
    with open(out_path, "w", encoding="utf-8") as h:
        json.dump(r1, h, sort_keys=True, separators=(",", ":"))
        h.write("\n")

    r0_num, r0_cat, r0_zf = (list(NUMERIC_FEATURES_V2),
                             list(CATEGORICAL_FEATURES_V2),
                             list(ZERO_FILL_FEATURES_V2))
    r1_num = r0_num + [n for n in S3.SEQ_FEATURES]
    models = {"logistic": LogisticModel, "hgb": HGBModel}
    sha = code_sha(base)
    data_sha = sha256_of_file(out_path)
    for rep, (ds, num, cat, zf) in {
            "R0": (v2, r0_num, r0_cat, r0_zf),
            "R1": (r1, r1_num, r0_cat, r0_zf)}.items():
        for mname, mcls in models.items():
            for target in (PRIMARY_TARGET, SECONDARY_TARGET):
                art = run_cell(
                    ds, f"{rep}-{mname}-{target}",
                    "V2" if rep == "R0" else "V3", num, cat, zf,
                    lambda names, _c=mcls: _c(names), target=target)
                cell_id = f"{args.experiment_id}-{rep}-{mname}-{target}"
                out = save_m2(base, cell_id, art, sha, data_sha,
                              args.overwrite, subdir=SEQUENCE_SUBDIR)
                print(f"{cell_id}: VALID Brier "
                      f"B0={art['b0']['valid']['brier']:.4f} "
                      f"M={art['model']['valid']['brier']:.4f} | TEST "
                      f"B0={art['b0']['test']['brier']:.4f} "
                      f"M={art['model']['test']['brier']:.4f} -> {out}")
                print(f"  fingerprint: {art['fingerprint']}")


if __name__ == "__main__":
    main()
