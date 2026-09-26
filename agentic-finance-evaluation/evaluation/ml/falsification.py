"""Falsification controls: permutation null + missingness-only probe.

Every ML cell gets a permutation control (TRAIN labels permuted with
the pre-registered seed, VALID/TEST untouched). A genuine signal must
degrade substantially under permutation; otherwise the evidence is NULL.

The missingness-only probe answers whether performance is explained by
missingness patterns (the M1 artefact) rather than environmental market
information: it trains the same adapter on missingness-indicator
features only.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Mapping

PERMUTATION_SEED = 20260926


def permute_labels(y_train: List[int], seed: int = PERMUTATION_SEED
                   ) -> List[int]:
    """Return a deranged-approximate permutation; never the identity."""
    rng = random.Random(seed)
    idx = list(range(len(y_train)))
    rng.shuffle(idx)
    if all(i == j for i, j in enumerate(idx)) and len(idx) > 1:
        idx[0], idx[1] = idx[1], idx[0]
    return [y_train[i] for i in idx]


def check_permutation_integrity(y_train: List[int], y_perm: List[int],
                                y_valid: List[int], y_test: List[int],
                                valid_copy: List[int], test_copy: List[int]
                                ) -> Dict[str, Any]:
    return {
        "train_labels_changed": y_perm != y_train,
        "train_label_sum_preserved": sum(y_perm) == sum(y_train),
        "valid_labels_untouched": list(y_valid) == list(valid_copy),
        "test_labels_untouched": list(y_test) == list(test_copy),
    }


def missingness_matrix(rows: List[Mapping[str, Any]],
                       numeric: List[str],
                       categorical: List[str]) -> List[List[float]]:
    """Indicator-only design matrix: 1.0 where the source value is None."""
    out = []
    for r in rows:
        feats = r["features"]
        vec: List[float] = []
        for name in numeric:
            vec.append(1.0 if feats.get(name) is None else 0.0)
        for name in categorical:
            val = feats.get(name)
            vec.append(1.0 if val is None or str(val).strip() == "" else 0.0)
        out.append(vec)
    return out
