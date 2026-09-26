"""TabPFN adapter (optional, isolated, graceful-skip).

TabPFN is a pre-existing pretrained tabular foundation model used here
purely as an evaluator-side diagnostic tool. It is NOT our contribution;
provenance/citation is recorded in every manifest that references it.

Observed environment status (2026-09-26, recorded — not asserted at
import time): ``tabpfn==9.0.0`` installs cleanly, but first use requires
gated HuggingFace weights (Prior-Labs/tabpfn_3_5) plus ``hf auth login``;
this sandbox has no token, no HF cache, and no working network route.
``availability_probe()`` therefore reports BLOCKED here, and any cell
requesting TabPFN persists blocker evidence instead of predictions.
The rest of the framework runs without TabPFN internals.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from evaluation.ml.models.base import BaseModel

TABPFN_PIN = "9.0.0"
TABPFN_SEED = 20260926
TABPFN_DEVICE = "cpu"
TABPFN_CITATION = (
    "TabPFN: a pretrained tabular foundation model (Hollmann, Mueller "
    "et al., Prior Labs; https://github.com/PriorLabs/TabPFN, "
    "https://docs.priorlabs.ai/how-to-access-gated-models). "
    "Used as an external diagnostic tool; not a contribution of this work.")


class TabPFNUnavailable(Exception):
    """Raised when the TabPFN backend cannot run; carries the reason."""


def availability_probe() -> Tuple[bool, str]:
    """Check the TabPFN backend without touching research data."""
    try:
        import tabpfn  # noqa: F401
    except ImportError as exc:
        return False, f"tabpfn package not installed: {exc}"
    try:
        import numpy as np
        from tabpfn import TabPFNClassifier
        model = TabPFNClassifier(device=TABPFN_DEVICE,
                                 random_state=TABPFN_SEED)
        tiny_x = np.array([[0.0, 1.0], [1.0, 0.0],
                           [2.0, 1.0], [1.0, 2.0]])
        tiny_y = np.array([0, 1, 0, 1])
        model.fit(tiny_x, tiny_y)
        model.predict_proba(tiny_x[:1])
        return True, "ok"
    except Exception as exc:  # gated weights, auth, network, device, ...
        return False, f"{type(exc).__name__}: {exc}"


class TabPFNModel(BaseModel):
    """Isolated TabPFN diagnostic behind the BaseModel boundary."""

    def __init__(self, feature_names: List[str],
                 device: str = TABPFN_DEVICE,
                 random_state: int = TABPFN_SEED) -> None:
        self.feature_names = list(feature_names)
        self.device = device
        self.random_state = random_state
        self._model: Any = None

    def fit(self, X: List[List[float]], y: List[int]) -> "TabPFNModel":
        try:
            from tabpfn import TabPFNClassifier
        except ImportError as exc:
            raise TabPFNUnavailable(
                f"tabpfn package not installed: {exc}") from exc
        try:
            import numpy as np
            self._model = TabPFNClassifier(
                device=self.device, random_state=self.random_state)
            self._model.fit(np.asarray(X, dtype=float),
                            np.asarray(y, dtype=int))
        except Exception as exc:
            raise TabPFNUnavailable(
                f"TabPFN backend unavailable: {type(exc).__name__}: {exc}"
            ) from exc
        return self

    def predict_proba(self, X: List[List[float]]) -> List[List[float]]:
        if self._model is None:
            raise ValueError("TabPFNModel used before fit")
        import numpy as np
        return [list(map(float, row)) for row in
                self._model.predict_proba(np.asarray(X, dtype=float))]

    def metadata(self) -> Dict[str, Any]:
        try:
            import tabpfn
            lib_version: Any = tabpfn.__version__
        except Exception:
            lib_version = f"unavailable (pin {TABPFN_PIN})"
        try:
            import torch
            torch_version: Any = torch.__version__
        except Exception:
            torch_version = "unavailable"
        return {"model_name": "TabPFNClassifier",
                "model_role": "capacity probe (external tool)",
                "library": "tabpfn",
                "library_version": lib_version,
                "torch_version": torch_version,
                "configuration": {"device": self.device,
                                  "n_estimators": "auto",
                                  "fit_mode": "fit_preprocessors"},
                "random_seed": self.random_state,
                "device": self.device,
                "citation": TABPFN_CITATION}
