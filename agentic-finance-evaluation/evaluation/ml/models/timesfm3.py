"""TimesFM-3.0 adapter (optional, isolated, graceful-skip).

Google TimesFM 3.0 (``google/timesfm-3.0-pytorch``), zero-shot
forecasting, CPU. Weights (1.32 GB) are distributed under the TimesFM
Non-Commercial License v1.0 — academic/non-commercial research use
only, documented in ``docs/ML_MODEL_LICENSES.md``. Weights download
to the HF cache outside the repository on first use; they are never
committed or redistributed.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.ml.forecasting.base import (
    FORECAST_QUANTILES, ForecastOutput,
)
from evaluation.ml.models.timeseries_base import (
    ModelStatus, ModelUnavailable, TimeSeriesModel,
)

TIMESFM_PACKAGE_PIN = "timesfm"
TIMESFM_PACKAGE_VERSION = "3.0.0"
TIMESFM_CHECKPOINT = "google/timesfm-3.0-pytorch"
TIMESFM_SEED = 20260926
TIMESFM_DEVICE = "cpu"
TIMESFM_LICENSE = "timesfm-non-commercial-license-v1.0"
# Native quantile-column order = package ForecastConfig default
# (timesfm3_forecaster.py: ``[0.1, ..., 0.9]``); verified at runtime.
TIMESFM_QUANTILE_LEVELS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
TIMESFM_CITATION = (
    "TimesFM 3.0: pretrained time-series foundation model (Google "
    "Research; https://huggingface.co/google/timesfm-3.0-pytorch, "
    "TimesFM Non-Commercial License v1.0, academic research use). "
    "Used as an external diagnostic tool; not a contribution of this work.")


class TimesFMUnavailable(ModelUnavailable):
    """TimesFM backend failure with machine-readable status."""


def _ensure_certs() -> None:
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    except ImportError:
        pass


def _load() -> Any:
    try:
        from timesfm import TimesFM3Forecaster
    except ImportError as exc:
        raise TimesFMUnavailable(
            ModelStatus.BLOCKED_MISSING_DEPENDENCY,
            f"timesfm not installed: {exc}") from exc
    _ensure_certs()
    try:
        return TimesFM3Forecaster.from_pretrained(
            TIMESFM_CHECKPOINT, device=TIMESFM_DEVICE)
    except (MemoryError, RuntimeError) as exc:
        if "memory" in str(exc).lower() or "oom" in str(exc).lower():
            raise TimesFMUnavailable(
                ModelStatus.RESOURCE_LIMIT,
                f"{type(exc).__name__}: {exc}") from exc
        raise TimesFMUnavailable(
            ModelStatus.BLOCKED_MISSING_WEIGHTS,
            f"{type(exc).__name__}: {exc}") from exc
    except Exception as exc:
        name = type(exc).__name__
        if "401" in str(exc) or "403" in str(exc) or "gated" in str(exc).lower():
            raise TimesFMUnavailable(
                ModelStatus.BLOCKED_AUTHORIZATION,
                f"{name}: {exc}") from exc
        raise TimesFMUnavailable(
            ModelStatus.BLOCKED_MISSING_WEIGHTS,
            f"{name}: {exc}") from exc


def _extract_paths(native: Any, horizon: int = 5
                   ) -> Tuple[Tuple[Optional[float], ...], ...]:
    """Map the native TimesFM3 output onto q10/q50/q90 paths.

    Inspects the runtime object (quantile arrays preferred; point
    forecast degrades q50-only with Nones elsewhere — never invented
    intervals).
    """
    quantile_arrays: Dict[float, Any] = {}
    native_q = getattr(native, "quantiles", None)
    try:
        import numpy as _np
        arr = _np.asarray(native_q, dtype=float)
        if arr.ndim == 2 and arr.shape[1] == len(TIMESFM_QUANTILE_LEVELS):
            # (horizon, level) matrix in TIMESFM_QUANTILE_LEVELS order.
            for j, level in enumerate(TIMESFM_QUANTILE_LEVELS):
                quantile_arrays[level] = arr[:, j]
    except Exception:
        pass
    for attr in ("quantile_forecasts", "quantile_preds"):
        if hasattr(native, attr):
            candidate = getattr(native, attr)
            if isinstance(candidate, dict):
                for k, v in candidate.items():
                    try:
                        quantile_arrays[float(k)] = v
                    except (TypeError, ValueError):
                        continue
    point = None
    for attr in ("mean", "point_forecast", "forecast", "prediction"):
        if hasattr(native, attr):
            point = getattr(native, attr)
            break
    if hasattr(native, "__iter__") and not hasattr(native, "_fields"):
        try:
            seq = list(native)
            if seq and all(isinstance(v, (int, float)) for v in seq):
                point = seq
        except TypeError:
            pass

    def _col(values: Any) -> Tuple[Optional[float], ...]:
        try:
            import numpy as np
            arr = np.asarray(values, dtype=float).ravel().tolist()
        except Exception:
            try:
                arr = [float(v) for v in list(values)]
            except Exception:
                return tuple([None] * horizon)
        out = [None if v != v else float(v) for v in arr[:horizon]]
        while len(out) < horizon:
            out.append(None)
        return tuple(out)

    paths = []
    for q in FORECAST_QUANTILES:
        best = None
        for k, v in quantile_arrays.items():
            if best is None or abs(k - q) < abs(best[0] - q):
                best = (k, v)
        if best is not None and abs(best[0] - q) < 1e-9:
            paths.append(_col(best[1]))
        elif q == 0.5 and point is not None:
            paths.append(_col(point))
        else:
            paths.append(tuple([None] * horizon))
    return tuple(paths)


def probe() -> Tuple[bool, str, str]:
    """Tiny synthetic round-trip (downloads weights on first success)."""
    try:
        import numpy as np
        model = _load()
        native = model.predict(
            context=np.array([float(i) for i in range(30)]),
            horizon=5, return_quantiles=True)
        paths = _extract_paths(native)
        assert len(paths) == 3
        del model
        _release_mem()
        return True, ModelStatus.AVAILABLE, "ok"
    except TimesFMUnavailable as exc:
        status = exc.args[0] if exc.args else ModelStatus.UNAVAILABLE
        return False, status, str(exc.args[1] if len(exc.args) > 1
                                  else exc)
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


class TimesFM3Model(TimeSeriesModel):
    """Isolated TimesFM-3.0 diagnostic behind the TimeSeriesModel boundary."""

    def __init__(self, device: str = TIMESFM_DEVICE,
                 random_state: int = TIMESFM_SEED) -> None:
        self.device = device
        self.random_state = random_state
        self._model: Any = None
        self._revision = "unresolved"

    def _ensure(self) -> Any:
        if self._model is None:
            self._model = _load()
            self._revision = _checkpoint_revision()
        return self._model

    def forecast(self, context: Mapping[str, Any]) -> ForecastOutput:
        import numpy as np
        series = [float(v) for v in context["series"]["close"]]
        model = self._ensure()
        try:
            native = model.predict(
                context=np.array(series), horizon=5,
                return_quantiles=True)
        except Exception as exc:
            raise TimesFMUnavailable(
                ModelStatus.UNAVAILABLE,
                f"{type(exc).__name__}: {exc}") from exc
        paths = _extract_paths(native)
        return ForecastOutput(
            model_id="timesfm3",
            model_version=_package_version(),
            checkpoint_revision=self._revision,
            decision_id=str(context.get("decision_id", "")),
            instrument=str(context.get("instrument", "")),
            decision_timestamp=str(context.get("decision_timestamp", "")),
            context_fingerprint=str(context["context_fingerprint"]),
            horizons=(1, 3, 5),
            quantiles=tuple(FORECAST_QUANTILES),
            quantile_paths=paths,
            reference_level=(float(series[-1]) if series else None),
            deterministic_seed=self.random_state,
            status=ModelStatus.AVAILABLE)

    def availability_probe(self) -> Tuple[bool, str, str]:
        return probe()

    def metadata(self) -> Dict[str, Any]:
        return {"model_name": "TimesFM3Forecaster",
                "model_role": "foundation forecasting diagnostic",
                "model_id": "timesfm3",
                "checkpoint_id": TIMESFM_CHECKPOINT,
                "checkpoint_revision": self._revision,
                "library": TIMESFM_PACKAGE_PIN,
                "library_version": _package_version(),
                "license": TIMESFM_LICENSE,
                "configuration": {"prediction_length": 5,
                                  "quantile_levels": list(
                                      FORECAST_QUANTILES),
                                  "univariate": True,
                                  "return_quantiles": True},
                "random_seed": self.random_state,
                "backend": "torch",
                "device": self.device,
                "citation": TIMESFM_CITATION}

    def release(self) -> None:
        self._model = None
        _release_mem()


def _package_version() -> str:
    try:
        import importlib.metadata as md
        return md.version(TIMESFM_PACKAGE_PIN)
    except Exception:
        return "unavailable"


def _checkpoint_revision() -> str:
    _ensure_certs()
    try:
        from huggingface_hub import HfApi
        info = HfApi().model_info(TIMESFM_CHECKPOINT)
        return str(info.sha or "unresolved")
    except Exception:
        return "unresolved"
