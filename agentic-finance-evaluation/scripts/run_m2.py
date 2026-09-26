"""Run the pre-registered M2 experiment and persist under _m2/.

Usage:
  python scripts/run_m2.py --experiment-id M2-20260926 [--overwrite]

Builds the V2 dataset from frozen E5A windows, reuses the frozen V1
combined dataset, executes M2a/M2b/M2c (+M2b secondary), and persists
one directory per cell under data/frozen_traces/_m2/.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, ".")

from evaluation.attribution import features_v2 as F2
from evaluation.attribution import m1_experiment as M1
from evaluation.attribution.persistence import sha256_of_file
from evaluation.ml import experiment as E
from evaluation.ml.persistence import save_m2

WINDOWS = [
    "data/frozen_traces/E5A-deterministic-attribution-20260926",
    "data/frozen_traces/E5A-window2-20260926",
    "data/frozen_traces/E5A-window3-20260926",
]
V1_DATASET = "data/frozen_traces/_ml/e5a_combined_v1.json"
V2_DATASET_OUT = "data/frozen_traces/_ml/e5a_combined_v2.json"


def code_sha(base_dir: str) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=base_dir,
                             capture_output=True, text=True, timeout=15)
        return out.stdout.strip() or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run pre-registered M2")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    with open(os.path.join(args.base_dir, V1_DATASET)) as h:
        v1 = json.load(h)
    print(f"V1 frozen dataset: {v1['manifest']['n_rows']} rows, "
          f"windows={v1['manifest']['windows']}")

    v2 = F2.build_ml_dataset_v2(WINDOWS, base_dir=args.base_dir)
    print(f"V2 dataset: {v2['manifest']['n_rows']} rows")
    for name, miss in sorted(v2["manifest"]["feature_missingness"].items()):
        print(f"  missing {name}: {miss}")
    out_path = os.path.join(args.base_dir, V2_DATASET_OUT)
    if os.path.exists(out_path) and not args.overwrite:
        raise FileExistsError(f"refusing to overwrite {out_path}")
    with open(out_path, "w", encoding="utf-8") as h:
        json.dump(v2, h, sort_keys=True, separators=(",", ":"))
        h.write("\n")

    cells = E.run_m2(v1, v2)
    sha = code_sha(args.base_dir)
    for cell_id, art in cells.items():
        data_sha = sha256_of_file(out_path)
        cell_exp_id = f"{args.experiment_id}-{cell_id}"
        if cell_id == "M2b_secondary":
            data_sha = sha256_of_file(out_path)
        out = save_m2(args.base_dir, cell_exp_id, art, sha, data_sha,
                      args.overwrite)
        status = art.get("status")
        if status == "COMPLETE":
            print(f"{cell_exp_id}: VALID Brier "
                  f"B0={art['b0']['valid']['brier']:.4f} "
                  f"M={art['model']['valid']['brier']:.4f} | TEST Brier "
                  f"B0={art['b0']['test']['brier']:.4f} "
                  f"M={art['model']['test']['brier']:.4f} -> {out}")
        else:
            print(f"{cell_exp_id}: {status} "
                  f"({art.get('blocker', {}).get('reason', '')[:160]}) "
                  f"-> {out}")
        print(f"  fingerprint: {art['fingerprint']}")


if __name__ == "__main__":
    main()
