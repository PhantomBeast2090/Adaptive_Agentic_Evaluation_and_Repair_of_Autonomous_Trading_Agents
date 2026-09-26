"""Base model interface for evaluator-side diagnostics."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseModel(ABC):
    """Minimal contract every diagnostic model must satisfy."""

    @abstractmethod
    def fit(self, X: List[List[float]], y: List[int]) -> "BaseModel":
        """Fit on TRAIN features/labels; return self."""

    @abstractmethod
    def predict_proba(self, X: List[List[float]]) -> List[List[float]]:
        """Return [[p0, p1], ...] with the same row count as X."""

    @abstractmethod
    def metadata(self) -> Dict[str, Any]:
        """Deterministic provenance: name, versions, config, seed, device."""
