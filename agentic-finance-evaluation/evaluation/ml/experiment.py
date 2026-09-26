"""M2 pre-registered experiment: 2x2 representation x capacity.

Frozen design (no tuning, no TEST contact during fitting):
  TRAIN = E5A-1, VALID = E5A-2, TEST = E5A-3 (temporal, never shuffled).
  Primary target: adverse_mae. Secondary target: adverse_forward_3d
  (M2b only; never selected on).
  Cells: M2a = V1 x TabPFN, M2b = V2 x Logistic, M2c = V2 x TabPFN.
  Frozen controls M1/B0 (V1 x Logistic / prevalence) already persist
  under _m1 and are re-read, never refit here.
  Every runnable cell gets a permutation null (seed 20260926, TRAIN
  labels only) plus a missingness-only probe.

Models are evaluator-side diagnostics, never trading policies. Nothing
here writes to MemoryStore.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from typing import Any, Callable, Dict, List, Mapping, Optional

from evaluation.attribution.features import DECISION_TIME_FEATURES
from evaluation.attribution.features_v2 import (
    CATEGORICAL_FEATURES_V2, DECISION_TIME_FEATURES_V2,
    NUMERIC_FEATURES_V2, ZERO_FILL_FEATURES_V2,
)
from evaluation.attribution.m1_experiment import (
    CATEGORICAL_FEATURES as V1_CATEGORICAL,
    NUMERIC_FEATURES as V1_NUMERIC,
    PERMUTATION_SEED,
    ZERO_FILL_FEATURES as V1_ZERO_FILL,
)
from evaluation.ml import evaluation as metrics
from evaluation.ml.diagnosis import FailureHypothesis
from evaluation.ml.falsification import (
    check_permutation_integrity, missingness_matrix, permute_labels,
)
from evaluation.ml.models.base import BaseModel
from evaluation.ml.models.logistic import LogisticModel
from evaluation.ml.models.tabpfn import (
    TabPFNModel, TabPFNUnavailable, availability_probe,
)
from evaluation.ml.persistence import fingerprint_artefacts

TRAIN_WINDOW = "E5A-deterministic-attribution-20260926"
VALID_WINDOW = "E5A-window2-20260926"
TEST_WINDOW = "E5A-window3-20260926"

PRIMARY_TARGET = "adverse_mae"
SECONDARY_TARGET = "adverse_forward_3d"


class Preprocessor:
    """TRAIN-fit preprocessing for an arbitrary frozen schema.

    Numerics: missing-indicator + median imputation (TRAIN median) +
    standardisation (TRAIN mean/std). Categoricals: one-hot over TRAIN
    categories; unseen -> all-zero. Zero-fill names map None -> 0.0
    (pre-first-fill flat semantics) while still tracking indicators.
    """

    def __init__(self, numeric: List[str], categorical: List[str],
                 zero_fill: List[str]) -> None:
        self.numeric = list(numeric)
        self.categorical = list(categorical)
        self.zero_fill = set(zero_fill)
        self.medians: Dict[str, float] = {}
        self.means: Dict[str, float] = {}
        self.stds: Dict[str, float] = {}
        self.categories: Dict[str, List[str]] = {}
        self.feature_names: List[str] = []

    def _num(self, row: Mapping[str, Any], name: str) -> Optional[float]:
        val = row.get(name)
        if val is None:
            return 0.0 if name in self.zero_fill else None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def fit(self, rows: List[Mapping[str, Any]]) -> "Preprocessor":
        feats = [r["features"] for r in rows]
        for name in self.numeric:
            present = [v for v in (self._num(f, name) for f in feats)
                       if v is not None]
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
        for name in self.categorical:
            self.categories[name] = sorted(
                set(str(f.get(name)) for f in feats))
        self.feature_names = []
        for name in self.numeric:
            self.feature_names += [name, f"{name}__missing"]
        for name in self.categorical:
            self.feature_names += [f"{name}={c}"
                                   for c in self.categories[name]]
        return self

    def transform(self, rows: List[Mapping[str, Any]]) -> List[List[float]]:
        out = []
        for r in rows:
            f = r["features"]
            vec: List[float] = []
            for name in self.numeric:
                v = self._num(f, name)
                vec.append(0.0 if v is None
                           else (v - self.means[name]) / self.stds[name])
                vec.append(1.0 if v is None else 0.0)
            for name in self.categorical:
                val = str(f.get(name))
                for c in self.categories[name]:
                    vec.append(1.0 if val == c else 0.0)
            out.append(vec)
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {"numeric": self.numeric, "categorical": self.categorical,
                "zero_fill": sorted(self.zero_fill),
                "medians": self.medians, "means": self.means,
                "stds": self.stds, "categories": self.categories,
                "feature_names": self.feature_names}


def split_dataset(ds: Mapping[str, Any], target: str
                  ) -> Dict[str, Any]:
    rows = ds["rows"]
    labelled = [r for r in rows if r["outcomes"].get(target) is not None]
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
            raise ValueError(f"split {name!r} is empty for target {target}")
        s.sort(key=lambda r: (r["keys"]["decision_timestamp"],
                              r["keys"]["decision_id"]))
    stamps = {n: [r["keys"]["decision_timestamp"] for r in s]
              for n, s in splits.items()}
    assert max(stamps["train"]) < min(stamps["valid"]) <= max(
        stamps["valid"]) < min(stamps["test"]), "temporal split violated"
    return {"splits": splits, "dropped_unlabelled": dropped}


def _schema_hash(feature_names: List[str]) -> str:
    return hashlib.sha256(
        json.dumps(sorted(feature_names), separators=(",", ":")).encode()
    ).hexdigest()


def _training_fingerprint(train_ids: List[str], target: str,
                          schema_hash: str) -> str:
    return hashlib.sha256(json.dumps(
        {"train_ids": sorted(train_ids), "target": target,
         "schema_hash": schema_hash},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _window_diagnostics(splits: Dict[str, List[Dict[str, Any]]],
                        target: str) -> Dict[str, Any]:
    from collections import Counter
    out = {}
    for name, rows in splits.items():
        y = [int(r["outcomes"][target]) for r in rows]
        out[name] = {
            "n": len(rows),
            "positives": sum(y),
            "prevalence": sum(y) / len(y) if y else None,
            "instruments": dict(Counter(
                str(r["features"].get("instrument")
                    if "instrument" in r["features"] else r["features"].get(
                        "active_context_version", "?"))
                for r in rows)),
            "missingness": {
                k: sum(1 for r in rows if r["features"].get(k) is None)
                for k in rows[0]["features"]},
        }
    return out


def _hypotheses(rows: List[Dict[str, Any]], probs: List[float],
                target: str, top_features: List[str], model_meta: Mapping,
                calib_meta: Mapping, schema_hash: str,
                train_fp: str) -> List[Dict[str, Any]]:
    out = []
    for r, p in zip(rows, probs):
        h = FailureHypothesis(
            decision_id=r["keys"]["decision_id"],
            experiment_id=r["keys"]["experiment_id"],
            decision_timestamp=r["keys"]["decision_timestamp"],
            target=target,
            predicted_adverse_probability=float(p),
            observed_target=(None if r["outcomes"].get(target) is None
                             else bool(r["outcomes"][target])),
            top_contributing_features=tuple(top_features),
            model_metadata=tuple(sorted(
                (k, str(v)) for k, v in dict(model_meta).items())),
            calibration_metadata=tuple(sorted(
                (k, str(v)) for k, v in dict(calib_meta).items())),
            feature_schema_hash=schema_hash,
            training_fingerprint=train_fp)
        out.append(h.to_dict())
    return out


def _base_name(encoded: str) -> str:
    if encoded.endswith("__missing"):
        return encoded[: -len("__missing")]
    if "=" in encoded:
        return encoded.split("=", 1)[0]
    return encoded


def run_cell(dataset: Mapping[str, Any],
             cell_id: str,
             schema_version: str,
             numeric: List[str],
             categorical: List[str],
             zero_fill: List[str],
             make_model: Callable[[List[str]], BaseModel],
             target: str = PRIMARY_TARGET,
             seed: int = PERMUTATION_SEED) -> Dict[str, Any]:
    """Execute one pre-registered cell; never touches TEST during fitting."""
    bundle = split_dataset(dataset, target)
    splits = bundle["splits"]
    y_train = [int(r["outcomes"][target]) for r in splits["train"]]
    y_valid = [int(r["outcomes"][target]) for r in splits["valid"]]
    y_test = [int(r["outcomes"][target]) for r in splits["test"]]
    prevalence = sum(y_train) / len(y_train)

    pre = Preprocessor(numeric, categorical, zero_fill).fit(splits["train"])
    schema_hash = _schema_hash(pre.feature_names)
    train_fp = _training_fingerprint(
        [r["keys"]["decision_id"] for r in splits["train"]],
        target, schema_hash)
    X_train = pre.transform(splits["train"])
    X_valid = pre.transform(splits["valid"])
    X_test = pre.transform(splits["test"])

    artefacts: Dict[str, Any] = {
        "config": {
            "cell_id": cell_id, "schema_version": schema_version,
            "feature_schema": list(pre.feature_names),
            "train_window": TRAIN_WINDOW, "valid_window": VALID_WINDOW,
            "test_window": TEST_WINDOW, "target": target,
            "adverse_band": 0.01, "permutation_seed": seed,
            "dropped_unlabelled": bundle["dropped_unlabelled"],
        },
        "preprocessing": pre.to_dict(),
        "splits": {k: [r["keys"]["decision_id"] for r in v]
                   for k, v in splits.items()},
        "diagnostics": _window_diagnostics(splits, target),
        "feature_schema_hash": schema_hash,
        "training_fingerprint": train_fp,
    }
    b0_valid = metrics.evaluate(y_valid, [prevalence] * len(y_valid))
    b0_test = metrics.evaluate(y_test, [prevalence] * len(y_test))
    artefacts["b0"] = {"train_prevalence": prevalence,
                       "valid": b0_valid, "test": b0_test}

    try:
        model = make_model(pre.feature_names)
        model.fit(X_train, y_train)
    except TabPFNUnavailable as exc:
        ok, probe_reason = availability_probe()
        artefacts["status"] = "BLOCKED"
        artefacts["blocker"] = {
            "reason": str(exc), "probe_ok": ok,
            "probe_reason": probe_reason,
            "model_metadata": (make_model(pre.feature_names).metadata()
                               if not ok else {})}
        artefacts["fingerprint"] = fingerprint_artefacts(artefacts)
        return artefacts

    p_valid = [float(row[1]) for row in model.predict_proba(X_valid)]
    p_test = [float(row[1]) for row in model.predict_proba(X_test)]
    m_valid = metrics.evaluate(y_valid, p_valid)
    m_test = metrics.evaluate(y_test, p_test)
    meta = model.metadata()

    if isinstance(model, LogisticModel):
        top = [_base_name(c["feature"])
               for c in model.coefficients()[:3]]
        extra = {"coefficients": model.coefficients(),
                 "intercept": model.intercept()}
    else:
        top = ["unavailable: non-linear adapter"]
        extra = {}

    # permutation null (TRAIN labels only; VALID/TEST untouched)
    y_perm = permute_labels(y_train, seed)
    perm_model = make_model(pre.feature_names)
    perm_model.fit(X_train, y_perm)
    pp_valid = [float(row[1]) for row in perm_model.predict_proba(X_valid)]
    pp_test = [float(row[1]) for row in perm_model.predict_proba(X_test)]
    perm_integrity = check_permutation_integrity(
        y_train, y_perm, y_valid, y_test, list(y_valid), list(y_test))

    # missingness-only probe (same adapter, indicator matrix only)
    miss_names = ([f"{n}__is_missing" for n in numeric]
                  + [f"{c}__is_missing" for c in categorical])
    miss_model = make_model(miss_names)
    miss_model.fit(missingness_matrix(splits["train"], numeric,
                                      categorical), y_train)
    mp_valid = [float(row[1]) for row in miss_model.predict_proba(
        missingness_matrix(splits["valid"], numeric, categorical))]
    mp_test = [float(row[1]) for row in miss_model.predict_proba(
        missingness_matrix(splits["test"], numeric, categorical))]

    calib = {"valid_brier": m_valid["brier"],
             "valid_prevalence": b0_valid["prevalence"],
             "train_prevalence": prevalence}
    artefacts["model"] = {"valid": m_valid, "test": m_test,
                          "metadata": meta, **extra}
    artefacts["metrics"] = {
        "b0": artefacts["b0"],
        "model": {"valid": m_valid, "test": m_test},
        "missingness_only": {
            "valid": metrics.evaluate(y_valid, mp_valid),
            "test": metrics.evaluate(y_test, mp_test)},
        "diagnostics": artefacts["diagnostics"]}
    artefacts["permutation"] = {
        "valid": metrics.evaluate(y_valid, pp_valid),
        "test": metrics.evaluate(y_test, pp_test),
        "integrity": perm_integrity}
    artefacts["missingness_only"] = {
        "valid": metrics.evaluate(y_valid, mp_valid),
        "test": metrics.evaluate(y_test, mp_test)}
    artefacts["predictions"] = {
        "valid": [{"decision_id": r["keys"]["decision_id"],
                   "label": int(r["outcomes"][target]), "p_adverse": p}
                  for r, p in zip(splits["valid"], p_valid)],
        "test": [{"decision_id": r["keys"]["decision_id"],
                  "label": int(r["outcomes"][target]), "p_adverse": p}
                 for r, p in zip(splits["test"], p_test)]}
    artefacts["hypotheses"] = {
        "valid": _hypotheses(splits["valid"], p_valid, target, top,
                             meta, calib, schema_hash, train_fp),
        "test": _hypotheses(splits["test"], p_test, target, top,
                            meta, calib, schema_hash, train_fp)}
    artefacts["status"] = "COMPLETE"
    artefacts["fingerprint"] = fingerprint_artefacts(artefacts)
    return artefacts


def run_m2(v1_dataset: Mapping[str, Any],
           v2_dataset: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Run the frozen 2x2 (primary target; secondary on M2b only)."""
    cells = {}
    cells["M2a"] = run_cell(
        v1_dataset, "M2a", "V1", list(V1_NUMERIC), list(V1_CATEGORICAL),
        list(V1_ZERO_FILL), lambda names: TabPFNModel(names),
        target=PRIMARY_TARGET)
    cells["M2b"] = run_cell(
        v2_dataset, "M2b", "V2", list(NUMERIC_FEATURES_V2),
        list(CATEGORICAL_FEATURES_V2), list(ZERO_FILL_FEATURES_V2),
        lambda names: LogisticModel(names), target=PRIMARY_TARGET)
    cells["M2b_secondary"] = run_cell(
        v2_dataset, "M2b_secondary", "V2", list(NUMERIC_FEATURES_V2),
        list(CATEGORICAL_FEATURES_V2), list(ZERO_FILL_FEATURES_V2),
        lambda names: LogisticModel(names), target=SECONDARY_TARGET)
    cells["M2c"] = run_cell(
        v2_dataset, "M2c", "V2", list(NUMERIC_FEATURES_V2),
        list(CATEGORICAL_FEATURES_V2), list(ZERO_FILL_FEATURES_V2),
        lambda names: TabPFNModel(names), target=PRIMARY_TARGET)
    return cells
