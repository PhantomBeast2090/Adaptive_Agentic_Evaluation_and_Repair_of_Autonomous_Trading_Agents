"""Time-series foundation-model interface (diagnostic use only).

``TimeSeriesModel`` is the forecasting-side counterpart of ``BaseModel``:
pretrained models produce PIT-valid forecast distributions; they never
see outcomes, never emit trading instructions, and never touch the
agent or MemoryStore. Resolution (AVAILABLE vs BLOCKED_*) is always
explicit — a blocked model is infrastructure evidence, never a
negative experimental result.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Mapping, Tuple

from evaluation.ml.forecasting.base import ForecastOutput


class ModelStatus:
    AVAILABLE = "AVAILABLE"
    BLOCKED_MISSING_DEPENDENCY = "BLOCKED_MISSING_DEPENDENCY"
    BLOCKED_MISSING_WEIGHTS = "BLOCKED_MISSING_WEIGHTS"
    BLOCKED_AUTHORIZATION = "BLOCKED_AUTHORIZATION"
    BLOCKED_LICENSE = "BLOCKED_LICENSE"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    UNAVAILABLE = "UNAVAILABLE"


class ModelUnavailable(Exception):
    """Base for all optional-model backends that cannot run.

    Carries machine-readable ``status`` (one of ModelStatus) plus a
    human reason. ``run_cell``-style harnesses catch this base class.
    """


class TimeSeriesModel(ABC):
    """Zero-shot forecasting diagnostic behind a uniform boundary."""

    @abstractmethod
    def forecast(self, context: Mapping[str, Any]) -> ForecastOutput:
        """Forecast from a PIT-valid context mapping; zero-shot only."""

    @abstractmethod
    def availability_probe(self) -> Tuple[bool, str, str]:
        """(ok, status, reason) without touching research data."""

    @abstractmethod
    def metadata(self) -> Dict[str, Any]:
        """Mandatory provenance: name/version/package/checkpoint/
        revision/license/backend/device/seed/configuration/schema hash."""

    @abstractmethod
    def release(self) -> None:
        """Drop resident weights; called between runs (RAM safety)."""
