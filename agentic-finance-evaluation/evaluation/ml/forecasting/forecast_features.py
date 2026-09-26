"""Forecast-derived diagnostic features (fixed schema, honest Nones).

Only quantities genuinely supported by quantile paths are derived.
Anything a model does not expose stays None — confidence is never
invented. Non-AVAILABLE forecasts yield an all-None row (missingness
preserved, never imputed).
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from evaluation.ml.forecasting.base import ForecastOutput

FORECAST_DERIVED_FEATURES = (
    "f_ret_1d",
    "f_ret_3d",
    "f_ret_5d",
    "f_q10_5d_ret",
    "f_q90_5d_ret",
    "f_interval_width_5d",
    "f_downside_prob",
    "f_slope",
    "f_curvature",
    "f_dispersion",
    "f_direction_consistency",
)


def _ret(level: Optional[float], ref: Optional[float]) -> Optional[float]:
    if level is None or ref in (None, 0):
        return None
    return (level - ref) / ref  # type: ignore[operator]


def _path(output: ForecastOutput, q: float) -> Optional[List[Optional[float]]]:
    try:
        i = list(output.quantiles).index(q)
    except ValueError:
        return None
    return list(output.quantile_paths[i])


def downside_probability(output: ForecastOutput) -> Optional[float]:
    """P(return <= 0) by linear interpolation over the quantile CDF."""
    ref = output.reference_level
    if ref in (None, 0):
        return None
    pairs = []
    for q, path in zip(output.quantiles, output.quantile_paths):
        if len(path) < 5 or path[4] is None:
            return None  # need the full 5d paths; partial CDF refused
        r = _ret(path[4], ref)
        if r is None:
            return None
        pairs.append((r, q))
    pairs.sort()
    if pairs[0][0] >= 0:
        return 0.0 if pairs[0][0] > 0 else pairs[0][1]
    if pairs[-1][0] <= 0:
        return 1.0
    for (r0, q0), (r1, q1) in zip(pairs, pairs[1:]):
        if r0 <= 0 <= r1:
            if r1 == r0:
                return (q0 + q1) / 2.0
            w = (0 - r0) / (r1 - r0)
            return q0 + w * (q1 - q0)
    return None


def derive(output: ForecastOutput) -> Dict[str, Optional[float]]:
    """Fixed-schema diagnostic row for one normalised forecast."""
    blank = {name: None for name in FORECAST_DERIVED_FEATURES}
    if output.status != "AVAILABLE":
        return blank
    ref = output.reference_level
    q50 = _path(output, 0.5)
    q10 = _path(output, 0.1)
    q90 = _path(output, 0.9)
    if q50 is None or len(q50) < 5:
        return blank
    rets = [_ret(q50[h - 1], ref) for h in (1, 3, 5)]
    if any(r is None for r in rets):
        return blank
    row: Dict[str, Optional[float]] = dict(blank)
    row["f_ret_1d"], row["f_ret_3d"], row["f_ret_5d"] = rets
    if q10 is not None and len(q10) >= 5 and q90 is not None \
            and len(q90) >= 5:
        row["f_q10_5d_ret"] = _ret(q10[4], ref)
        row["f_q90_5d_ret"] = _ret(q90[4], ref)
        if row["f_q10_5d_ret"] is not None \
                and row["f_q90_5d_ret"] is not None:
            row["f_interval_width_5d"] = (
                row["f_q90_5d_ret"] - row["f_q10_5d_ret"])  # type: ignore[operator]
    row["f_downside_prob"] = downside_probability(output)
    slope = (rets[2] - rets[0]) / 4.0  # type: ignore[operator]
    row["f_slope"] = slope
    row["f_curvature"] = (rets[2] - 2 * rets[1] + rets[0])  # type: ignore[operator]
    widths: List[float] = []
    for h in range(5):
        lo = _path(output, 0.1)
        hi = _path(output, 0.9)
        if lo is None or hi is None:
            break
        r_lo, r_hi = _ret(lo[h], ref), _ret(hi[h], ref)
        if r_lo is None or r_hi is None:
            break
        widths.append(r_hi - r_lo)
    row["f_dispersion"] = (sum(widths) / len(widths)) if widths else None
    signs = [1 if r > 0 else (-1 if r < 0 else 0) for r in rets]
    row["f_direction_consistency"] = (
        sum(1 for s in signs if s == signs[2]) / 3.0)
    return row


def feature_provenance() -> Mapping[str, Any]:
    return {"source": "ForecastOutput.quantile_paths (model-derived)",
            "pit_rule": "context strictly < T; returns vs last PIT close",
            "derivation": "q50 path returns; interval/CDF/slope/curvature "
                          "from q10/q50/q90 full 5d paths only",
            "agent_observes": "no",
            "missingness": "None whenever model/paths unsupported"}
