"""HistGradientBoosting classical-nonlinear control (M3, no tuning).

Fixed configuration chosen once for determinism and small-sample
sanity (no search, no TEST contact): limited leaves/iterations, fixed
seed. Exists to isolate linear-vs-nonlinear tabular capacity from
foundation-model representation effects — not to win a leaderboard.
"""

from __future__ import annotations

from typing import Any, Dict, List

from evaluation.ml.models.base import BaseModel

HGB_MAX_ITER = 200
HGB_LEARNING_RATE = 0.1
HGB_MAX_LEAF_NODES = 31
HGB_MIN_SAMPLES_LEAF = 5
HGB_L2 = 1.0
HGB_SEED = 20260926


class HGBModel(BaseModel):
    """Deterministic gradient-boosting diagnostic (controls M3)."""

    def __init__(self, feature_names: List[str]) -> None:
        self.feature_names = list(feature_names)
        self._model: Any = None

    def fit(self, X: List[List[float]], y: List[int]) -> "HGBModel":
        from sklearn.ensemble import HistGradientBoostingClassifier
        self._model = HistGradientBoostingClassifier(
            max_iter=HGB_MAX_ITER,
            learning_rate=HGB_LEARNING_RATE,
            max_leaf_nodes=HGB_MAX_LEAF_NODES,
            min_samples_leaf=HGB_MIN_SAMPLES_LEAF,
            l2_regularization=HGB_L2,
            early_stopping=False,
            random_state=HGB_SEED)
        self._model.fit(X, y)
        return self

    def predict_proba(self, X: List[List[float]]) -> List[List[float]]:
        if self._model is None:
            raise ValueError("HGBModel used before fit")
        return [list(map(float, row))
                for row in self._model.predict_proba(X)]

    def metadata(self) -> Dict[str, Any]:
        import sklearn
        return {"model_name": "HistGradientBoostingClassifier",
                "model_role": "classical nonlinear control (M3)",
                "library": "scikit-learn",
                "library_version": sklearn.__version__,
                "configuration": {"max_iter": HGB_MAX_ITER,
                                  "learning_rate": HGB_LEARNING_RATE,
                                  "max_leaf_nodes": HGB_MAX_LEAF_NODES,
                                  "min_samples_leaf": HGB_MIN_SAMPLES_LEAF,
                                  "l2_regularization": HGB_L2,
                                  "early_stopping": False},
                "random_seed": HGB_SEED,
                "device": "cpu",
                "citation": "scikit-learn; no external model claimed"}
