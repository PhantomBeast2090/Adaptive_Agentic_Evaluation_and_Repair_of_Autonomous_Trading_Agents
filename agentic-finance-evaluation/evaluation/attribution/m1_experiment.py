"""M1 logistic-regression diagnostic experiment (pre-registered).

Research question: given only decision-time information, can a learned
model predict whether an executed trading decision will experience an
adverse outcome (adverse_MAE), out-of-sample, beyond prevalence?

Frozen design (no tuning, no TEST contact during fitting):
  TRAIN = E5A-1, VALID = E5A-2, TEST = E5A-3 (temporal, never shuffled).
  B0 = TRAIN prevalence constant predictor (primary null).
  M1 = plain logistic regression (lbfgs, C=1.0 fixed, no search).
  Permutation null: TRAIN labels permuted with a recorded seed, retrained,
  evaluated on VALID/TEST as a falsification sanity check.

The model is an evaluator-side diagnostic, not a trading policy.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from typing import Any, Dict, List, Mapping, Optional, Tuple

PERMUTATION_SEED = 20260926
LOGREG_C = 1.0

TRAIN_WINDOW = "E5A-deterministic-attribution-20260926"
VALID_WINDOW = "E5A-window2-20260926"
TEST_WINDOW = "E5A-window3-20260926"

NUMERIC_FEATURES = (
    "pre_trend_1d", "pre_trend_3d", "pre_trend_5d", "vix_tm1",
    "cash_before", "position_qty", "exposure_before", "avg_cost",
    "realized_pnl_before", "unrealized_pnl_before",
    "total_equity_before", "quantity",
)
CATEGORICAL_FEATURES = ("instrument", "action")

# Pre-first-fill semantics: absent position/avg_cost means flat (zero),
# not unknown. Declared here so train/valid/test share one rule.
ZERO_FILL_FEATURES = ("position_qty", "avg_cost")


class Preprocessor:
    """TRAIN-fit preprocessing. Fit on TRAIN only; transform is pure.

    Numerics: missing-indicator column + median imputation (TRAIN median)
    + standardisation (TRAIN mean/std; zero-variance -> scale 1.0, still
    deterministic). Categoricals: one-hot over TRAIN categories; unseen
    categories map to the all-zero vector (deterministic, no failure).
    """

    def __init__(self) -> None:
        self.medians: Dict[str, float] = {}
        self.means: Dict[str, float] = {}
        self.stds: Dict[str, float] = {}
        self.categories: Dict[str, List[str]] = {}
        self.feature_names: List[str] = []

    def _num(self, row: Mapping[str, Any], name: str) -> Optional[float]:
        val = row.get(name)
        if val is None:
            if name in ZERO_FILL_FEATURES:
                return 0.0
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def fit(self, rows: List[Mapping[str, Any]]) -> "Preprocessor":
        feats = [r["features"] for r in rows]
        for name in NUMERIC_FEATURES:
            vals = [self._num(f, name) for f in feats]
            present = [v for v in vals if v is not None]
            if not present:
                raise ValueError(f"feature {name!r} unavailable in TRAIN")
            s = sorted(present)
            median = s[len(s) // 2] if len(s) % 2 else (
                s[len(s) // 2 - 1] + s[len(s) // 2]) / 2.0
            mean = sum(present) / len(present)
            var = sum((v - mean) ** 2 for v in present) / len(present)
            self.medians[name] = median
            self.means[name] = mean
            self.stds[name] = math.sqrt(var) if var > 0 else 1.0
        for name in CATEGORICAL_FEATURES:
            cats = sorted(set(str(f.get(name)) for f in feats))
            self.categories[name] = cats
        self.feature_names = []
        for name in NUMERIC_FEATURES:
            self.feature_names += [name, f"{name}__missing"]
        for name in CATEGORICAL_FEATURES:
            self.feature_names += [f"{name}={c}" for c in self.categories[name]]
        return self

    def transform(self, rows: List[Mapping[str, Any]]) -> List[List[float]]:
        out = []
        for r in rows:
            f = r["features"]
            vec: List[float] = []
            for name in NUMERIC_FEATURES:
                v = self._num(f, name)
                vec.append(0.0 if v is None else (v - self.means[name]) / self.stds[name])
                vec.append(1.0 if v is None else 0.0)
            for name in CATEGORICAL_FEATURES:
                val = str(f.get(name))
                for c in self.categories[name]:
                    vec.append(1.0 if val == c else 0.0)
            out.append(vec)
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {"medians": self.medians, "means": self.means,
                "stds": self.stds, "categories": self.categories,
                "feature_names": self.feature_names}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Preprocessor":
        p = cls()
        p.medians = dict(payload["medians"])
        p.means = dict(payload["means"])
        p.stds = dict(payload["stds"])
        p.categories = {k: list(v) for k, v in payload["categories"].items()}
        p.feature_names = list(payload["feature_names"])
        return p


def load_dataset(path: str) -> Dict[str, Any]:
    with open(path) as handle:
        return json.load(handle)


def split_dataset(ds: Mapping[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Temporal split by window. Rows with missing adverse_mae label are
    excluded from all splits (never label-manufactured); counts recorded."""
    rows = ds["rows"]
    labelled = [r for r in rows if r["outcomes"].get("adverse_mae") is not None]
    dropped = len(rows) - len(labelled)
    splits = {
        "train": [r for r in labelled
                  if r["keys"]["experiment_id"] == TRAIN_WINDOW],
        "valid": [r for r in labelled
                  if r["keys"]["experiment_id"] == VALID_WINDOW],
        "test": [r for r in labelled
                 if r["keys"]["experiment_id"] == TEST_WINDOW],
    }
    for name, s in splits.items():
        if not s:
            raise ValueError(f"split {name!r} is empty")
        s.sort(key=lambda r: (r["keys"]["decision_timestamp"],
                              r["keys"]["decision_id"]))
    return {"splits": splits, "dropped_unlabelled": dropped}


def brier_score(y: List[int], p: List[float]) -> float:
    return sum((pi - yi) ** 2 for pi, yi in zip(p, y)) / len(y)


def log_loss(y: List[int], p: List[float]) -> float:
    eps = 1e-15
    total = 0.0
    for pi, yi in zip(p, y):
        q = min(max(pi, eps), 1 - eps)
        total += -(yi * math.log(q) + (1 - yi) * math.log(1 - q))
    return total / len(y)


def reliability(y: List[int], p: List[float], n_bins: int = 5) -> List[Dict[str, Any]]:
    order = sorted(range(len(p)), key=lambda i: p[i])
    bins = [order[i::n_bins] for i in range(n_bins)]
    out = []
    for b in bins:
        if not b:
            continue
        out.append({"n": len(b),
                    "mean_predicted": sum(p[i] for i in b) / len(b),
                    "mean_observed": sum(y[i] for i in b) / len(b)})
    return out


def evaluate(y: List[int], p: List[float]) -> Dict[str, Any]:
    return {"n": len(y), "positives": sum(y),
            "prevalence": sum(y) / len(y) if y else None,
            "brier": brier_score(y, p), "log_loss": log_loss(y, p),
            "reliability": reliability(y, p)}


def fit_logreg(X: List[List[float]], y: List[int]) -> Any:
    from sklearn.linear_model import LogisticRegression
    model = LogisticRegression(C=LOGREG_C, max_iter=5000)
    model.fit(X, y)
    return model


def run_m1(dataset_path: str, seed: int = PERMUTATION_SEED) -> Dict[str, Any]:
    """Execute the full pre-registered M1 protocol; return artefacts dict."""
    ds = load_dataset(dataset_path)
    bundle = split_dataset(ds)
    splits = bundle["splits"]
    y_train = [int(r["outcomes"]["adverse_mae"]) for r in splits["train"]]
    prevalence = sum(y_train) / len(y_train)

    pre = Preprocessor().fit(splits["train"])
    X_train = pre.transform(splits["train"])
    X_valid = pre.transform(splits["valid"])
    X_test = pre.transform(splits["test"])
    y_valid = [int(r["outcomes"]["adverse_mae"]) for r in splits["valid"]]
    y_test = [int(r["outcomes"]["adverse_mae"]) for r in splits["test"]]

    b0_valid = evaluate(y_valid, [prevalence] * len(y_valid))
    b0_test = evaluate(y_test, [prevalence] * len(y_test))

    model = fit_logreg(X_train, y_train)
    p_valid = [float(v) for v in model.predict_proba(X_valid)[:, 1]]
    p_test = [float(v) for v in model.predict_proba(X_test)[:, 1]]
    m1_valid = evaluate(y_valid, p_valid)
    m1_test = evaluate(y_test, p_test)

    import random
    rng = random.Random(seed)
    perm_idx = list(range(len(y_train)))
    rng.shuffle(perm_idx)
    y_perm = [y_train[i] for i in perm_idx]
    perm_model = fit_logreg(X_train, y_perm)
    pp_valid = [float(v) for v in perm_model.predict_proba(X_valid)[:, 1]]
    pp_test = [float(v) for v in perm_model.predict_proba(X_test)[:, 1]]
    perm_valid = evaluate(y_valid, pp_valid)
    perm_test = evaluate(y_test, pp_test)

    coefs = [
        {"feature": name, "coefficient": float(c)}
        for name, c in zip(pre.feature_names, model.coef_[0])]
    coefs.sort(key=lambda d: -abs(d["coefficient"]))

    def pred_rows(split_rows: List[Dict[str, Any]],
                  probs: List[float]) -> List[Dict[str, Any]]:
        return [{"decision_id": r["keys"]["decision_id"],
                 "experiment_id": r["keys"]["experiment_id"],
                 "decision_timestamp": r["keys"]["decision_timestamp"],
                 "label": int(r["outcomes"]["adverse_mae"]),
                 "p_adverse": p}
                for r, p in zip(split_rows, probs)]

    artefacts = {
        "config": {
            "train_window": TRAIN_WINDOW, "valid_window": VALID_WINDOW,
            "test_window": TEST_WINDOW, "target": "adverse_mae",
            "adverse_band": 0.01, "model": "logistic_regression",
            "C": LOGREG_C, "solver": "lbfgs",
            "permutation_seed": seed, "dataset": dataset_path,
            "dropped_unlabelled": bundle["dropped_unlabelled"],
        },
        "preprocessing": pre.to_dict(),
        "splits": {k: [r["keys"]["decision_id"] for r in v]
                   for k, v in splits.items()},
        "b0": {"train_prevalence": prevalence,
               "valid": b0_valid, "test": b0_test},
        "m1": {"valid": m1_valid, "test": m1_test,
               "coefficients": coefs,
               "intercept": float(model.intercept_[0])},
        "permutation": {"valid": perm_valid, "test": perm_test},
        "predictions": {
            "valid_m1": pred_rows(splits["valid"], p_valid),
            "test_m1": pred_rows(splits["test"], p_test),
            "valid_perm": pred_rows(splits["valid"], pp_valid),
            "test_perm": pred_rows(splits["test"], pp_test),
        },
    }
    artefacts["fingerprint"] = fingerprint_artefacts(artefacts)
    return artefacts


def fingerprint_artefacts(artefacts: Mapping[str, Any]) -> str:
    payload = {k: v for k, v in artefacts.items() if k != "fingerprint"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def save_m1(base_dir: str, experiment_id: str,
            artefacts: Mapping[str, Any],
            code_sha: str, data_sha: str,
            overwrite: bool = False) -> str:
    """Persist M1 under data/frozen_traces/_m1/<experiment_id>/ (tracked)."""
    out_dir = os.path.join(base_dir, "data", "frozen_traces", "_m1", experiment_id)
    if os.path.exists(out_dir) and not overwrite:
        raise FileExistsError(f"refusing to overwrite {out_dir}")
    os.makedirs(out_dir, exist_ok=True)

    def write(name: str, payload: Any) -> None:
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as h:
            json.dump(payload, h, sort_keys=True, separators=(",", ":"))
            h.write("\n")

    write("config.json", artefacts["config"])
    write("preprocessing.json", artefacts["preprocessing"])
    write("splits.json", artefacts["splits"])
    write("metrics_b0.json", artefacts["b0"])
    write("metrics_m1.json", artefacts["m1"])
    write("metrics_permutation.json", artefacts["permutation"])
    write("predictions.json", artefacts["predictions"])
    write("manifest.json", {
        "experiment_id": experiment_id,
        "fingerprint": artefacts["fingerprint"],
        "code_sha": code_sha, "data_sha": data_sha})
    return out_dir


def main() -> None:
    import argparse
    import subprocess

    parser = argparse.ArgumentParser(description="Run pre-registered M1")
    parser.add_argument("--dataset", default="data/frozen_traces/_ml/e5a_combined_v1.json")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    artefacts = run_m1(os.path.join(args.base_dir, args.dataset))
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=args.base_dir,
                             capture_output=True, text=True,
                             timeout=15).stdout.strip() or "UNKNOWN"
    except Exception:
        sha = "UNKNOWN"
    from evaluation.attribution.persistence import sha256_of_file
    data_sha = sha256_of_file(os.path.join(args.base_dir, args.dataset))
    out = save_m1(args.base_dir, args.experiment_id, artefacts, sha,
                  data_sha, args.overwrite)
    print(f"M1 {args.experiment_id}: "
          f"valid Brier B0={artefacts['b0']['valid']['brier']:.4f} "
          f"M1={artefacts['m1']['valid']['brier']:.4f} | "
          f"test Brier B0={artefacts['b0']['test']['brier']:.4f} "
          f"M1={artefacts['m1']['test']['brier']:.4f} -> {out}")
    print(f"fingerprint: {artefacts['fingerprint']}")


if __name__ == "__main__":
    main()
