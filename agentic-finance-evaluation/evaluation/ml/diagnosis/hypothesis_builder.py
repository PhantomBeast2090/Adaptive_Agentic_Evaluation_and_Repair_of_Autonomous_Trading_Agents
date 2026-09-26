"""Miner condition -> DiagnosticHypothesis -> FailureHypothesis.

The translator preserves the existing repair pipeline: the extended
diagnostic object is the working representation, and
``to_failure_hypothesis`` projects it onto the frozen
``FailureHypothesis`` contract that existing validation understands.
Projection is lossy by design (documented mapping); the full object
persists alongside for audit.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Mapping

from evaluation.ml.diagnosis.failure_hypothesis import (
    CANDIDATE, DiagnosticHypothesis,
)
from evaluation.ml.diagnosis.hypothesis import FailureHypothesis
from evaluation.ml.diagnosis.forecast_diagnostics import INFERRED


def _fingerprint(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def from_condition(candidate: Mapping[str, Any],
                   train_rows: List[Mapping[str, Any]],
                   windows: List[str],
                   model_metadata: Mapping[str, Any],
                   forecast_fingerprint: str,
                   information_set_fingerprint: str,
                   target: str,
                   hypothesis_id: str) -> DiagnosticHypothesis:
    """Build a CANDIDATE hypothesis from one mined condition."""
    cond = tuple(candidate["condition"])
    instruments = sorted(set(
        str(r["features"].get("instrument")) for r in train_rows
        if all(_matches(r, c) for c in cond)))
    actions = sorted(set(
        str((r.get("keys") or {}).get("action", "BUY")) for r in train_rows
        if all(_matches(r, c) for c in cond)))
    tr = candidate["train"]
    clauses = ", ".join(cond)
    mechanism = (
        f"INFERRED: decisions satisfying [{clauses}] exhibit adverse "
        f"{target} rate {tr['rate']:.3f} (n={tr['n']}) vs TRAIN baseline "
        f"{tr['baseline']:.3f} (delta {tr['delta']:+.3f}). "
        f"VALID confirmation rate {candidate['valid']['rate']:.3f} "
        f"(n={candidate['valid']['n']}). No trading action prescribed.")
    return DiagnosticHypothesis(
        hypothesis_id=hypothesis_id,
        target=target,
        decision_scope=tuple(windows),
        instrument_scope=tuple(instruments),
        action_scope=tuple(actions) if actions else ("BUY",),
        condition=cond,
        mechanism=mechanism,
        expected_failure_mode=target,
        observed_adverse_rate=float(tr["rate"]),
        baseline_adverse_rate=float(tr["baseline"]),
        effect_delta=float(tr["delta"]),
        forecast_evidence=tuple(sorted(
            (c, "MODEL_DERIVED") for c in cond if c.startswith("f_"))),
        temporal_support=tuple([
            ("train", f"n={tr['n']} rate={tr['rate']:.3f}"),
            ("valid", f"n={candidate['valid']['n']} "
                      f"rate={candidate['valid']['rate']:.3f}"),
            ("test", f"n={candidate['test']['n']} "
                     f"rate={candidate['test']['rate']}"),
        ]),
        sample_count=int(tr["n"]),
        calibration=tuple(sorted([
            ("train_baseline", str(tr["baseline"])),
            ("forecast_fingerprint", forecast_fingerprint),
        ])),
        model_metadata=tuple(sorted(
            (k, str(v)) for k, v in dict(model_metadata).items())),
        feature_provenance=tuple(sorted(
            (c, ("MODEL_DERIVED" if c.startswith("f_") else "OBSERVED"))
            for c in cond)),
        information_set_fingerprint=information_set_fingerprint,
        provenance_class=INFERRED,
        status=CANDIDATE,
    )


def _matches(row: Mapping[str, Any], clause: str) -> bool:
    col, _, band = clause.partition("=")
    val = row["features"].get(col)
    if col == "instrument":
        return str(val) == band
    try:
        v = float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    lo, hi = _band_cache.get(col, (None, None))
    if band == "low":
        return lo is not None and v <= lo
    if band == "high":
        return hi is not None and v >= hi
    return lo is not None and hi is not None and lo < v < hi


_band_cache: Dict[str, Any] = {}


def set_band_cache(spec: Mapping[str, Any]) -> None:
    _band_cache.clear()
    for col, bands in spec.get("bands", {}).items():
        if bands is not None:
            _band_cache[col] = (bands["lo"], bands["hi"])


def to_failure_hypothesis(dh: DiagnosticHypothesis,
                          representative_decision_id: str,
                          experiment_id: str,
                          decision_timestamp: str,
                          observed_target: Any = None
                          ) -> FailureHypothesis:
    """Project onto the frozen FailureHypothesis contract.

    Mapping: condition clauses -> top_contributing_features; mechanism
    summary + rates -> calibration_metadata; model metadata passed
    through. The projection carries no outcome into agent-visible
    fields (observed_target stays evaluator-side on this object).
    """
    calib = list(dh.calibration) + [
        ("observed_adverse_rate", str(dh.observed_adverse_rate)),
        ("baseline_adverse_rate", str(dh.baseline_adverse_rate)),
        ("effect_delta", str(dh.effect_delta)),
        ("hypothesis_id", dh.hypothesis_id),
        ("provenance_class", dh.provenance_class),
    ]
    return FailureHypothesis(
        decision_id=representative_decision_id,
        experiment_id=experiment_id,
        decision_timestamp=decision_timestamp,
        target=dh.target,
        predicted_adverse_probability=float(dh.observed_adverse_rate),
        observed_target=observed_target,
        top_contributing_features=tuple(
            c.split("=")[0] for c in dh.condition),
        model_metadata=tuple(dh.model_metadata),
        calibration_metadata=tuple(sorted(calib)),
        feature_schema_hash=dh.information_set_fingerprint,
        training_fingerprint=dh.information_set_fingerprint,
    )
