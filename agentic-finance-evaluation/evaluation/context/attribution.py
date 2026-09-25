"""E4-O metric-level outcome attribution (E4-owned, analysis only).

Operates exclusively on frozen 25-metric vectors from completed
artefacts. Performs no episodes, builds no counterfactual
trajectories, invents no per-trade skill, and feeds nothing back into
memory or context. Every quantity is one of:

* OBSERVED — read verbatim from the artefact (`None` preserved);
* NORMALISED — deterministic arithmetic on observed values;
* BENCHMARK — an explicitly assumption-based descriptive mechanical
  benchmark, never described as causal;
* RESIDUAL — arithmetic difference under the benchmark, never
  described as skill or improvement.

Undefined inputs propagate as ``None``; nothing is imputed and zero
denominators yield ``None``, never an invented value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.contracts.fingerprints import fingerprint_of_dict

ATTRIBUTION_METHOD = "metric-level-attribution"
ATTRIBUTION_VERSION = "v1"

OUTCOME_ENDPOINTS = (
    "cumulative_return",
    "max_drawdown",
    "sharpe_per_session",
)
ACTIVITY_VARIABLES = (
    "order_count",
    "turnover",
    "inactivity_rate",
    "gross_exposure_max",
    "gross_exposure_mean",
)


@dataclass(frozen=True)
class CellAttribution:
    """Observed + normalised outcome quantities for one arm/window cell."""

    arm: str
    window: str
    observed: Mapping[str, Any]
    activity_share: Optional[float]
    turnover_normalised_return: Optional[float]
    exposure_normalised_return: Optional[float]
    fragile_sharpe: bool
    method: str = ATTRIBUTION_METHOD
    method_version: str = ATTRIBUTION_VERSION

    def __post_init__(self) -> None:
        for field_name in ("arm", "window"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        if not isinstance(self.observed, Mapping):
            raise TypeError("observed must be a mapping")
        for field_name in ("method", "method_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "arm": self.arm,
            "window": self.window,
            "observed": dict(self.observed),
            "activity_share": self.activity_share,
            "turnover_normalised_return": self.turnover_normalised_return,
            "exposure_normalised_return": self.exposure_normalised_return,
            "fragile_sharpe": bool(self.fragile_sharpe),
            "method": self.method,
            "version": self.method_version,
        }

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return float(value)


def activity_share(metrics: Mapping[str, Any]) -> Optional[float]:
    """Share of sessions with submitted orders (1 - inactivity)."""
    if not isinstance(metrics, Mapping):
        raise TypeError("metrics must be a mapping")
    inactivity = _finite(metrics.get("inactivity_rate"))
    if inactivity is None:
        return None
    return 1.0 - inactivity


def turnover_normalised_return(
    metrics: Mapping[str, Any],
) -> Optional[float]:
    """Return per unit turnover; None when undefined or turnover is zero."""
    if not isinstance(metrics, Mapping):
        raise TypeError("metrics must be a mapping")
    ret = _finite(metrics.get("cumulative_return"))
    turnover = _finite(metrics.get("turnover"))
    if ret is None or turnover is None or turnover == 0.0:
        return None
    return ret / turnover


def exposure_normalised_return(
    metrics: Mapping[str, Any],
) -> Optional[float]:
    """Return per unit mean exposure; None when undefined or zero."""
    if not isinstance(metrics, Mapping):
        raise TypeError("metrics must be a mapping")
    ret = _finite(metrics.get("cumulative_return"))
    exposure = _finite(metrics.get("gross_exposure_mean"))
    if ret is None or exposure is None or exposure == 0.0:
        return None
    return ret / exposure


def sharpe_is_fragile(
    metrics: Mapping[str, Any], *, min_active_share: float = 0.2
) -> bool:
    """Whether Sharpe rests on too little activity to interpret.

    A Sharpe computed over a window where the active share falls below
    ``min_active_share`` is flagged fragile: a handful of active
    sessions cannot support decision-quality inference. Flagging is
    descriptive, never a pass/fail judgement.
    """
    if not isinstance(metrics, Mapping):
        raise TypeError("metrics must be a mapping")
    share = activity_share(metrics)
    if share is None:
        return True
    return bool(share < min_active_share)


def attribute_cell(
    arm: str, window: str, metrics: Mapping[str, Any]
) -> CellAttribution:
    """Build the observed + normalised record for one cell (pure)."""
    if not isinstance(metrics, Mapping):
        raise TypeError("metrics must be a mapping")
    observed = {
        name: (None if value is None else _finite(value))
        for name, value in metrics.items()
    }
    return CellAttribution(
        arm=arm,
        window=window,
        observed=observed,
        activity_share=activity_share(metrics),
        turnover_normalised_return=turnover_normalised_return(metrics),
        exposure_normalised_return=exposure_normalised_return(metrics),
        fragile_sharpe=sharpe_is_fragile(metrics),
    )


def mechanical_benchmark(
    reference_metrics: Mapping[str, Any],
    context_metrics: Mapping[str, Any],
) -> Dict[str, Any]:
    """Assumption-based mechanical benchmark (descriptive, not causal).

    Assumption stated explicitly: had the reference arm traded at the
    context arm's exposure scale with unchanged per-exposure outcome
    rate, its return would scale linearly with mean exposure. Under
    that assumption, compares the observed context return against the
    scaled reference return. The residual is analytical only.
    """
    for name, mapping in (
        ("reference_metrics", reference_metrics),
        ("context_metrics", context_metrics),
    ):
        if not isinstance(mapping, Mapping):
            raise TypeError(f"{name} must be a mapping")
    ref_ret = _finite(reference_metrics.get("cumulative_return"))
    ref_exp = _finite(reference_metrics.get("gross_exposure_mean"))
    ctx_ret = _finite(context_metrics.get("cumulative_return"))
    ctx_exp = _finite(context_metrics.get("gross_exposure_mean"))
    if (
        ref_ret is None
        or ref_exp is None
        or ref_exp == 0.0
        or ctx_ret is None
        or ctx_exp is None
    ):
        return {
            "assumption": (
                "linear exposure scaling of the reference outcome rate"
            ),
            "expected_context_return": None,
            "observed_context_return": ctx_ret,
            "residual": None,
            "residual_defined": False,
        }
    expected = ref_ret * (ctx_exp / ref_exp)
    return {
        "assumption": (
            "linear exposure scaling of the reference outcome rate"
        ),
        "expected_context_return": expected,
        "observed_context_return": ctx_ret,
        "residual": ctx_ret - expected,
        "residual_defined": True,
    }


def paired_metric_delta(
    map_a: Mapping[str, Any], map_b: Mapping[str, Any]
) -> Dict[str, Optional[float]]:
    """Descriptive B - A deltas over the metric union (None-preserving)."""
    if not isinstance(map_a, Mapping) or not isinstance(map_b, Mapping):
        raise TypeError("metric maps must be mappings")
    deltas: Dict[str, Optional[float]] = {}
    for name in sorted(set(map_a) | set(map_b)):
        first = _finite(map_a.get(name))
        second = _finite(map_b.get(name))
        if first is None or second is None:
            deltas[name] = None
        else:
            deltas[name] = second - first
    return deltas


def attribution_fingerprint(attributions: Mapping[str, Any]) -> str:
    """Deterministic fingerprint over an attribution record mapping."""
    if not isinstance(attributions, Mapping):
        raise TypeError("attributions must be a mapping")
    return fingerprint_of_dict(dict(attributions))


__all__ = [
    "ACTIVITY_VARIABLES",
    "ATTRIBUTION_METHOD",
    "ATTRIBUTION_VERSION",
    "OUTCOME_ENDPOINTS",
    "CellAttribution",
    "activity_share",
    "attribution_fingerprint",
    "exposure_normalised_return",
    "mechanical_benchmark",
    "paired_metric_delta",
    "sharpe_is_fragile",
    "turnover_normalised_return",
]
