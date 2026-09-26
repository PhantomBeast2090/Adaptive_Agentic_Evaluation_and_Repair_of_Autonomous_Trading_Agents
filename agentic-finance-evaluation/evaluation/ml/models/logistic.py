"""Logistic control adapter (frozen M1 semantics, no tuning).

Wraps ``sklearn.linear_model.LogisticRegression`` with the exact M1
configuration (lbfgs, C=1.0, max_iter=5000) so every M2 cell using this
adapter is directly comparable to the frozen M1 control.
"""

from __future__ import annotations

from typing import Any, Dict, List

from evaluation.ml.models.base import BaseModel

LOGREG_C = 1.0
LOGREG_SOLVER = "lbfgs"
LOGREG_MAX_ITER = 5000


class LogisticModel(BaseModel):
    """Deterministic logistic-regression diagnostic."""

    def __init__(self, feature_names: List[str]) -> None:
        self.feature_names = list(feature_names)
        self._model: Any = None

    def fit(self, X: List[List[float]], y: List[int]) -> "LogisticModel":
        from sklearn.linear_model import LogisticRegression
        self._model = LogisticRegression(
            C=LOGREG_C, solver=LOGREG_SOLVER, max_iter=LOGREG_MAX_ITER)
        self._model.fit(X, y)
        return self

    def predict_proba(self, X: List[List[float]]) -> List[List[float]]:
        if self._model is None:
            raise ValueError("LogisticModel used before fit")
        return [list(map(float, row))
                for row in self._model.predict_proba(X)]

    def coefficients(self) -> List[Dict[str, Any]]:
        if self._model is None:
            raise ValueError("LogisticModel used before fit")
        coefs = [{"feature": n, "coefficient": float(c)}
                 for n, c in zip(self.feature_names, self._model.coef_[0])]
        coefs.sort(key=lambda d: -abs(d["coefficient"]))
        return coefs

    def intercept(self) -> float:
        if self._model is None:
            raise ValueError("LogisticModel used before fit")
        return float(self._model.intercept_[0])

    def metadata(self) -> Dict[str, Any]:
        import sklearn
        return {"model_name": "logistic_regression",
                "model_role": "control (frozen M1 semantics)",
                "library": "scikit-learn",
                "library_version": sklearn.__version__,
                "configuration": {"C": LOGREG_C, "solver": LOGREG_SOLVER,
                                  "max_iter": LOGREG_MAX_ITER},
                "random_seed": None,
                "device": "cpu",
                "citation": "frozen M1 control; no external model claimed"}
