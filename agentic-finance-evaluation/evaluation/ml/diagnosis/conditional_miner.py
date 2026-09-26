"""Conditional diagnostic miner (transparent, TRAIN-only fitting).

Candidate space (fixed, pre-registered):
  * single numeric tercile bands from TRAIN quantiles (cut points frozen
    for VALID/TEST),
  * instrument equality,
  * pairwise conjunctions (band x band, band x instrument) with
    TRAIN N >= MIN_TRAIN_N.

Selection uses TRAIN (+VALID confirmation) only, never TEST:
candidate iff TRAIN N >= MIN_TRAIN_N, TRAIN absolute delta >=
MIN_TRAIN_DELTA, and VALID rate > VALID baseline (same direction).
Top MAX_CANDIDATES by TRAIN delta. TEST is purely held-out reporting.

No p-values, no threshold shopping: bands come from TRAIN terciles.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple

from evaluation.ml.diagnosis.forecast_diagnostics import (
    MINER_CATEGORICAL_COLUMNS, MINER_NUMERIC_COLUMNS,
)

MIN_TRAIN_N = 15
MIN_TRAIN_DELTA = 0.02
MAX_CANDIDATES = 5


def _terciles(values: List[float]) -> Tuple[float, float]:
    s = sorted(values)
    n = len(s)
    return s[n // 3], s[(2 * n) // 3]


def fit_bands(train_rows: List[Mapping[str, Any]]
              ) -> Dict[str, Any]:
    """TRAIN-only band cut points + baseline prevalence."""
    bands = {}
    for col in MINER_NUMERIC_COLUMNS:
        vals = [r["features"][col] for r in train_rows
                if r["features"].get(col) is not None]
        if len(vals) < 3:
            bands[col] = None  # insufficient TRAIN support: column inert
        else:
            lo, hi = _terciles(vals)
            bands[col] = {"lo": lo, "hi": hi}
    cats: Dict[str, List[str]] = {}
    for col in MINER_CATEGORICAL_COLUMNS:
        cats[col] = sorted(set(str(r["features"].get(col))
                               for r in train_rows))
    y = [r["outcome"] for r in train_rows if r.get("outcome") is not None]
    return {"bands": bands, "categories": cats,
            "train_baseline": (sum(1 for v in y if v) / len(y)) if y else None,
            "train_n": len(y)}


def _band_of(col: str, value: Any, bands: Mapping[str, Any]) -> Optional[str]:
    spec = bands.get(col)
    if spec is None or value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= spec["lo"]:
        return "low"
    if v >= spec["hi"]:
        return "high"
    return "mid"


def _conditions_for(row: Mapping[str, Any], spec: Mapping[str, Any]
                    ) -> List[Tuple[str, ...]]:
    feats = row["features"]
    singles: List[Tuple[str, ...]] = []
    for col in MINER_NUMERIC_COLUMNS:
        b = _band_of(col, feats.get(col), spec["bands"])
        if b is not None:
            singles.append((f"{col}={b}",))
    for col in MINER_CATEGORICAL_COLUMNS:
        singles.append((f"{col}={feats.get(col)}",))
    conds = list(singles)
    for i in range(len(singles)):
        for j in range(i + 1, len(singles)):
            first_cols = {c.split("=")[0] for c in singles[i]}
            second_cols = {c.split("=")[0] for c in singles[j]}
            if first_cols & second_cols:
                continue
            conds.append(tuple(sorted(singles[i] + singles[j])))
    return conds


def _rate(rows: List[Mapping[str, Any]],
          cond: Tuple[str, ...],
          spec: Mapping[str, Any]) -> Tuple[int, int]:
    n = k = 0
    allowed = set(cond)
    for r in rows:
        if r.get("outcome") is None:
            continue
        if all(c in _conditions_flat(r, spec) for c in allowed):
            n += 1
            k += 1 if r["outcome"] else 0
    return n, k


def _conditions_flat(row: Mapping[str, Any],
                     spec: Mapping[str, Any]) -> List[str]:
    return [c for cond in _conditions_for(row, spec) for c in cond]


def mine(train_rows: List[Mapping[str, Any]],
         valid_rows: List[Mapping[str, Any]],
         test_rows: List[Mapping[str, Any]],
         target: str) -> Dict[str, Any]:
    """Discover conditions on TRAIN, confirm on VALID, report TEST."""
    spec = fit_bands(train_rows)
    train_base = spec["train_baseline"]
    if train_base is None:
        return {"spec": spec, "candidates": [], "target": target,
                "status": "NO_TRAIN_LABELS"}

    def split_rate(rows: List[Mapping[str, Any]]) -> Optional[float]:
        y = [r["outcome"] for r in rows if r.get("outcome") is not None]
        return (sum(1 for v in y if v) / len(y)) if y else None

    valid_base = split_rate(valid_rows)
    test_base = split_rate(test_rows)

    universe: Dict[Tuple[str, ...], None] = {}
    for r in train_rows:
        for cond in _conditions_for(r, spec):
            universe.setdefault(cond)
    candidates = []
    for cond in universe:
        n_tr, k_tr = _rate(train_rows, cond, spec)
        if n_tr < MIN_TRAIN_N:
            continue
        rate_tr = k_tr / n_tr
        delta_tr = rate_tr - train_base
        if delta_tr < MIN_TRAIN_DELTA:
            continue
        n_va, k_va = _rate(valid_rows, cond, spec)
        rate_va = (k_va / n_va) if n_va else None
        if rate_va is None or valid_base is None \
                or not (rate_va > valid_base):
            continue  # no VALID confirmation: not a candidate
        n_te, k_te = _rate(test_rows, cond, spec)
        candidates.append({
            "condition": list(cond),
            "train": {"n": n_tr, "k": k_tr, "rate": rate_tr,
                      "baseline": train_base, "delta": delta_tr},
            "valid": {"n": n_va, "k": k_va, "rate": rate_va,
                      "baseline": valid_base,
                      "delta": rate_va - valid_base},
            "test": {"n": n_te, "k": k_te,
                     "rate": (k_te / n_te) if n_te else None,
                     "baseline": test_base,
                     "delta": ((k_te / n_te - test_base)
                               if n_te and test_base is not None else None)},
        })
    candidates.sort(key=lambda c: -c["train"]["delta"])
    return {"spec": spec, "candidates": candidates[:MAX_CANDIDATES],
            "n_universe": len(universe), "target": target,
            "status": "COMPLETE"}
