"""Verification-gate foundation (M-R1, additive).

Reuses the frozen verification triple (ValidationReport,
RegressionAnalysis, RepairResult) and the `_decide` acceptance policy
without modification. Adds the statistical evidence helpers the final
gate requires:

  paired_bootstrap_ci   i.i.d. bootstrap CI over paired per-session
                        differences (deterministic seed).
  block_bootstrap_ci    stationary-style block bootstrap for
                        session-ordered series (dependence-aware).
  coverage_precheck     support gate: the repair must fire often enough
                        to be evaluable.
  assemble_verification compose triple + statistics + persistence proof
                        into a RepairVerification whose verdict defaults
                        to NSF (insufficient evidence never commits).

A bootstrap lower bound is an EVIDENCE GATE, never mathematical proof:
trading series violate the stationarity/mixing assumptions behind the
asymptotics. The gate is conservative by construction (NSF default).
"""

from __future__ import annotations

import math
import random
from typing import Any, Mapping, Sequence, Tuple

from evaluation.repair.schemas import RepairVerification


def _check_series(values: Sequence[float], name: str) -> Tuple[float, ...]:
    cleaned = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} must contain only numbers")
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            raise ValueError(f"{name} must be finite")
        cleaned.append(number)
    if not cleaned:
        raise ValueError(f"{name} must be non-empty")
    return tuple(cleaned)


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    if not 0.0 <= pct <= 100.0:
        raise ValueError("pct must be in [0, 100]")
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = pct / 100.0 * (len(sorted_values) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return sorted_values[low]
    frac = rank - low
    return sorted_values[low] * (1.0 - frac) + sorted_values[high] * frac


def paired_bootstrap_ci(
    differences: Sequence[float],
    seed: int,
    n_boot: int = 2000,
    alpha: float = 0.05,
) -> Mapping[str, Any]:
    """Bootstrap CI over paired per-session (repaired − base) differences."""
    values = _check_series(differences, "differences")
    if isinstance(n_boot, bool) or n_boot < 100:
        raise ValueError("n_boot must be an integer >= 100")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    rng = random.Random(seed)
    n = len(values)
    means = sorted(
        sum(values[rng.randrange(n)] for _ in range(n)) / n
        for _ in range(n_boot)
    )
    return {
        "method": "paired-bootstrap",
        "n": n,
        "n_boot": n_boot,
        "seed": seed,
        "alpha": alpha,
        "mean": sum(values) / n,
        "lower": _percentile(means, 100.0 * alpha / 2.0),
        "upper": _percentile(means, 100.0 * (1.0 - alpha / 2.0)),
    }


def block_bootstrap_ci(
    series: Sequence[float],
    seed: int,
    block_len: int = 5,
    n_boot: int = 2000,
    alpha: float = 0.05,
) -> Mapping[str, Any]:
    """Block bootstrap CI over one session-ordered metric series.

    Resamples contiguous blocks (wrapping at the end) to preserve local
    dependence. ``block_len`` should follow Politis–White-style selection;
    the caller records the choice in provenance.
    """
    values = _check_series(series, "series")
    if isinstance(block_len, bool) or block_len < 1:
        raise ValueError("block_len must be a positive integer")
    if isinstance(n_boot, bool) or n_boot < 100:
        raise ValueError("n_boot must be an integer >= 100")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    rng = random.Random(seed)
    n = len(values)
    length = min(block_len, n)
    means = []
    for _ in range(n_boot):
        total = 0.0
        count = 0
        while count < n:
            start = rng.randrange(n)
            for offset in range(length):
                if count >= n:
                    break
                total += values[(start + offset) % n]
                count += 1
        means.append(total / n)
    means.sort()
    return {
        "method": "block-bootstrap",
        "n": n,
        "block_len": length,
        "n_boot": n_boot,
        "seed": seed,
        "alpha": alpha,
        "mean": sum(values) / n,
        "lower": _percentile(means, 100.0 * alpha / 2.0),
        "upper": _percentile(means, 100.0 * (1.0 - alpha / 2.0)),
    }


def coverage_precheck(fire_count: int, min_fires: int) -> Mapping[str, Any]:
    """Support gate: a repair that never fires cannot be evaluated."""
    if isinstance(fire_count, bool) or not isinstance(fire_count, int):
        raise TypeError("fire_count must be an integer")
    if isinstance(min_fires, bool) or not isinstance(min_fires, int):
        raise TypeError("min_fires must be an integer")
    return {
        "fire_count": fire_count,
        "min_fires": min_fires,
        "passed": fire_count >= min_fires,
    }


def assemble_verification(
    verification_id: str,
    candidate_fingerprint: str,
    validation_fingerprint: str = "",
    regression_fingerprint: str = "",
    decision_fingerprint: str = "",
    metric_deltas: Mapping[str, Any] | None = None,
    bootstrap_ci: Mapping[str, Any] | None = None,
    persistence_fingerprint: str = "",
    accepted: bool = False,
    provenance: Mapping[str, Any] | None = None,
) -> RepairVerification:
    """Compose a RepairVerification; verdict NSF unless accepted is True.

    ``accepted=True`` may only be passed when the frozen `_decide`
    policy returned ACCEPTED AND every M-R1 evidence helper passed; the
    composition records the claim but never invents it.
    """
    return RepairVerification(
        verification_id=verification_id,
        candidate_fingerprint=candidate_fingerprint,
        validation_fingerprint=validation_fingerprint,
        regression_fingerprint=regression_fingerprint,
        decision_fingerprint=decision_fingerprint,
        metric_deltas=dict(metric_deltas or {}),
        bootstrap_ci=dict(bootstrap_ci or {}),
        persistence_fingerprint=persistence_fingerprint,
        verdict="ACCEPT" if accepted else "NSF",
        provenance=dict(provenance or {}),
    )
