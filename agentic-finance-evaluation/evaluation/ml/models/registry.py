"""Model registry: uniform status resolution for every diagnostic model.

Importing this module never imports torch, Chronos, TimesFM, or any
optional dependency — each entry resolves lazily inside its probe.
Plain ``pytest`` collection is therefore safe without weights.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

from evaluation.ml.models.timeseries_base import ModelStatus


def _tabular_entry(import_path: str, probe_path: str) -> Dict[str, Any]:
    return {"kind": "tabular", "import_path": import_path,
            "probe_path": probe_path, "license": "bundled-scikit-learn"}


REGISTRY: Dict[str, Dict[str, Any]] = {
    "logistic": _tabular_entry(
        "evaluation.ml.models.logistic:LogisticModel",
        "evaluation.ml.models.logistic:LogisticModel"),
    "hgb": _tabular_entry(
        "evaluation.ml.models.hist_gradient_boosting:HGBModel",
        "evaluation.ml.models.hist_gradient_boosting:HGBModel"),
    "tabpfn": {"kind": "tabular",
               "import_path": "evaluation.ml.models.tabpfn:TabPFNModel",
               "probe_path": "evaluation.ml.models.tabpfn:availability_probe",
               "license": "prior-labs-gated"},
    "chronos2": {"kind": "forecast",
                 "import_path": "evaluation.ml.models.chronos2:Chronos2Model",
                 "probe_path": "evaluation.ml.models.chronos2:probe",
                 "license": "Apache-2.0"},
    "timesfm3": {"kind": "forecast",
                 "import_path": "evaluation.ml.models.timesfm3:TimesFM3Model",
                 "probe_path": "evaluation.ml.models.timesfm3:probe",
                 "license": "timesfm-non-commercial-license-v1.0"},
}


def _call(path: str, *args: Any) -> Any:
    mod_name, attr = path.split(":")
    import importlib
    mod = importlib.import_module(mod_name)
    return getattr(mod, attr)(*args)


def status_of(model_id: str) -> Tuple[str, str, Dict[str, Any]]:
    """(status, reason, metadata-or-evidence) without research data."""
    entry = REGISTRY.get(model_id)
    if entry is None:
        return (ModelStatus.UNAVAILABLE, f"unknown model {model_id!r}", {})
    try:
        if entry["kind"] == "tabular" and model_id in ("logistic", "hgb"):
            cls = _call(entry["import_path"], ["_probe"])
            meta = cls.metadata()
            return ModelStatus.AVAILABLE, "ok", meta
        outcome = _call(entry["probe_path"])
        if isinstance(outcome, tuple) and len(outcome) == 3:
            ok, status, reason = outcome
            return (ModelStatus.AVAILABLE, reason, {}) if ok else (
                status, reason, {})
        ok, reason = outcome
        return ((ModelStatus.AVAILABLE, reason, {}) if ok
                else (ModelStatus.UNAVAILABLE, reason, {}))
    except Exception as exc:
        return (ModelStatus.UNAVAILABLE,
                f"{type(exc).__name__}: {exc}", {})


def describe() -> List[Dict[str, Any]]:
    out = []
    for model_id, entry in REGISTRY.items():
        status, reason, _ = status_of(model_id)
        out.append({"model_id": model_id, "kind": entry["kind"],
                    "license": entry["license"], "status": status,
                    "reason": reason})
    return out


def make_tabular(model_id: str, feature_names: List[str]) -> Any:
    cls = _call(REGISTRY[model_id]["import_path"], feature_names)
    return cls
