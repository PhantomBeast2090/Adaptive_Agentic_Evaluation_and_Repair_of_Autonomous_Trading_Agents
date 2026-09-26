"""Chronos-2 adapter (optional, isolated, graceful-skip).

Amazon Chronos-2 (``amazon/chronos-2``), Apache-2.0, zero-shot
univariate forecasting. Authorised fallback on resource limits:
``autogluon/chronos-2-small`` (28M) — recorded explicitly in metadata,
never silently substituted. Weights download to the HF cache outside
the repository on first use; they are never committed.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Mapping, Tuple

from evaluation.ml.forecasting.base import (
    FORECAST_QUANTILES, ForecastOutput,
)
from evaluation.ml.models.timeseries_base import (
    ModelStatus, ModelUnavailable, TimeSeriesModel,
)

CHRONOS_PACKAGE_PIN = "chronos-forecasting"
CHRONOS_PRIMARY = "amazon/chronos-2"
CHRONOS_FALLBACK = "autogluon/chronos-2-small"
CHRONOS_SEED = 20260926
CHRONOS_DEVICE = "cpu"
CHRONOS_LICENSE = "Apache-2.0"
CHRONOS_CITATION = (
    "Chronos-2: pretrained time-series foundation model (Amazon; "
    "https://huggingface.co/amazon/chronos-2, Apache-2.0). "
    "Used as an external diagnostic tool; not a contribution of this work.")


class ChronosUnavailable(ModelUnavailable):
    """Chronos backend failure with machine-readable status."""


def _ensure_certs() -> None:
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    except ImportError:
        pass


def _load(checkpoint: str) -> Any:
    try:
        from chronos import Chronos2Pipeline
    except ImportError as exc:
        raise ChronosUnavailable(
            ModelStatus.BLOCKED_MISSING_DEPENDENCY,
            f"chronos-forecasting not installed: {exc}") from exc
    _ensure_certs()
    try:
        import torch
        torch.manual_seed(CHRONOS_SEED)
        return Chronos2Pipeline.from_pretrained(
            checkpoint, device_map=CHRONOS_DEVICE)
    except (MemoryError, RuntimeError) as exc:
        if "memory" in str(exc).lower() or "oom" in str(exc).lower():
            raise ChronosUnavailable(
                ModelStatus.RESOURCE_LIMIT,
                f"{type(exc).__name__}: {exc}") from exc
        raise ChronosUnavailable(
            ModelStatus.BLOCKED_MISSING_WEIGHTS,
            f"{type(exc).__name__}: {exc}") from exc
    except Exception as exc:
        raise ChronosUnavailable(
            ModelStatus.BLOCKED_MISSING_WEIGHTS,
            f"{type(exc).__name__}: {exc}") from exc


def probe() -> Tuple[bool, str, str]:
    """Tiny synthetic round-trip (downloads weights on first success)."""
    try:
        pipe = _load(CHRONOS_PRIMARY)
    except ChronosUnavailable as exc:
        status = exc.args[0] if exc.args else ModelStatus.UNAVAILABLE
        return False, status, str(exc.args[1] if len(exc.args) > 1
                                  else exc)
    try:
        import pandas as pd
        df = pd.DataFrame({
            "item_id": ["probe"] * 30,
            "timestamp": pd.date_range("2023-01-01", periods=30, freq="D"),
            "target": [float(i) for i in range(30)]})
        out = pipe.predict_df(
            df, prediction_length=5,
            quantile_levels=list(FORECAST_QUANTILES),
            freq="D")
        assert len(out) >= 5
        del pipe
        _release_mem()
        return True, ModelStatus.AVAILABLE, "ok"
    except Exception as exc:
        return False, ModelStatus.UNAVAILABLE, (
            f"{type(exc).__name__}: {exc}")


def _release_mem() -> None:
    import gc
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


class Chronos2Model(TimeSeriesModel):
    """Isolated Chronos-2 diagnostic behind the TimeSeriesModel boundary."""

    def __init__(self, checkpoint: str = CHRONOS_PRIMARY,
                 device: str = CHRONOS_DEVICE,
                 random_state: int = CHRONOS_SEED) -> None:
        self.checkpoint = checkpoint
        self.device = device
        self.random_state = random_state
        self._pipe: Any = None
        self._resolved_checkpoint = checkpoint
        self._revision = "unresolved"

    def _ensure(self) -> Any:
        if self._pipe is not None:
            return self._pipe
        try:
            self._pipe = _load(self.checkpoint)
        except ChronosUnavailable as exc:
            status = exc.args[0] if exc.args else ModelStatus.UNAVAILABLE
            if status == ModelStatus.RESOURCE_LIMIT \
                    and self.checkpoint == CHRONOS_PRIMARY:
                # Authorised fallback, explicitly recorded downstream.
                self._pipe = _load(CHRONOS_FALLBACK)
                self._resolved_checkpoint = CHRONOS_FALLBACK
            else:
                raise
        self._revision = _checkpoint_revision(self._resolved_checkpoint)
        return self._pipe

    def forecast(self, context: Mapping[str, Any]) -> ForecastOutput:
        import pandas as pd
        series = list(context["series"]["close"])
        stamps = list(context["stamps"]["close"])
        pipe = self._ensure()
        df = pd.DataFrame({
            "item_id": ["series"] * len(series),
            "timestamp": pd.to_datetime(stamps),
            "target": [float(v) for v in series]})
        try:
            out = pipe.predict_df(
                df, prediction_length=5,
                quantile_levels=list(FORECAST_QUANTILES),
                freq="D")  # values-only model; freq extends timestamps alone
        except Exception as exc:
            raise ChronosUnavailable(
                ModelStatus.UNAVAILABLE,
                f"{type(exc).__name__}: {exc}") from exc
        rows = out[out["item_id"] == "series"].tail(5)
        paths = []
        for q in FORECAST_QUANTILES:
            col = str(q) if str(q) in rows.columns else f"{q:.1f}"
            vals = [None if pd.isna(v) else float(v)
                    for v in rows[col].tolist()]
            while len(vals) < 5:
                vals.append(None)
            paths.append(tuple(vals[:5]))
        return ForecastOutput(
            model_id="chronos2",
            model_version=_package_version(),
            checkpoint_revision=self._revision,
            decision_id=str(context.get("decision_id", "")),
            instrument=str(context.get("instrument", "")),
            decision_timestamp=str(context.get("decision_timestamp", "")),
            context_fingerprint=str(context["context_fingerprint"]),
            horizons=(1, 3, 5),
            quantiles=tuple(FORECAST_QUANTILES),
            quantile_paths=tuple(paths),
            reference_level=(float(series[-1]) if series else None),
            deterministic_seed=self.random_state,
            status=ModelStatus.AVAILABLE)

    def availability_probe(self) -> Tuple[bool, str, str]:
        return probe()

    def metadata(self) -> Dict[str, Any]:
        return {"model_name": "Chronos2Pipeline",
                "model_role": "foundation forecasting diagnostic",
                "model_id": "chronos2",
                "checkpoint_id": self._resolved_checkpoint,
                "checkpoint_requested": self.checkpoint,
                "checkpoint_revision": self._revision,
                "fallback_used": self._resolved_checkpoint != self.checkpoint,
                "library": CHRONOS_PACKAGE_PIN,
                "library_version": _package_version(),
                "license": CHRONOS_LICENSE,
                "configuration": {"prediction_length": 5,
                                  "quantile_levels": list(
                                      FORECAST_QUANTILES),
                                  "univariate": True},
                "random_seed": self.random_state,
                "backend": "torch",
                "device": self.device,
                "citation": CHRONOS_CITATION}

    def release(self) -> None:
        self._pipe = None
        _release_mem()


def _package_version() -> str:
    try:
        import importlib.metadata as md
        return md.version(CHRONOS_PACKAGE_PIN)
    except Exception:
        return "unavailable"


def _checkpoint_revision(checkpoint: str) -> str:
    _ensure_certs()
    try:
        from huggingface_hub import HfApi
        info = HfApi().model_info(checkpoint)
        return str(info.sha or "unresolved")
    except Exception:
        return "unresolved"
