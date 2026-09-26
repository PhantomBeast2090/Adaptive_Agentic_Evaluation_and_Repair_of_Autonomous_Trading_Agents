"""M2 metrics. Brier score is primary (calibrated adverse-risk
estimation); log-loss/reliability are secondary calibration views;
AUROC/AUPRC are secondary discrimination views. Accuracy is not used.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List


def brier_score(y: List[int], p: List[float]) -> float:
    return sum((pi - yi) ** 2 for pi, yi in zip(p, y)) / len(y)


def log_loss(y: List[int], p: List[float]) -> float:
    eps = 1e-15
    total = 0.0
    for pi, yi in zip(p, y):
        q = min(max(pi, eps), 1 - eps)
        total += -(yi * math.log(q) + (1 - yi) * math.log(1 - q))
    return total / len(y)


def reliability(y: List[int], p: List[float], n_bins: int = 5
                ) -> List[Dict[str, Any]]:
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


def _rank_metric(y: List[int], p: List[float], kind: str) -> Any:
    if len(set(y)) < 2:
        return None  # single-class split: rank metrics undefined
    try:
        from sklearn.metrics import average_precision_score, roc_auc_score
        if kind == "auroc":
            return float(roc_auc_score(y, p))
        return float(average_precision_score(y, p))
    except Exception:
        return None


def evaluate(y: List[int], p: List[float]) -> Dict[str, Any]:
    return {"n": len(y), "positives": sum(y),
            "prevalence": sum(y) / len(y) if y else None,
            "brier": brier_score(y, p), "log_loss": log_loss(y, p),
            "reliability": reliability(y, p),
            "auroc": _rank_metric(y, p, "auroc"),
            "auprc": _rank_metric(y, p, "auprc")}
