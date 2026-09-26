"""Diagnostic hypothesis schema (extends, never replaces, FailureHypothesis).

``DiagnosticHypothesis`` carries the full §15 contract including the
condition, effect sizes, and per-field provenance classes
(OBSERVED / INFERRED / EVALUATOR_ONLY / MODEL_DERIVED). It is still
evaluator-side evidence: ``status`` starts at CANDIDATE and only the
existing validation/admission machinery may advance it. Nothing here
writes to MemoryStore.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

CANDIDATE = "CANDIDATE"


@dataclass(frozen=True)
class DiagnosticHypothesis:
    """One discovered failure condition with complete provenance."""

    hypothesis_id: str
    target: str
    decision_scope: Tuple[str, ...]      # window ids covered
    instrument_scope: Tuple[str, ...]    # instruments observed under condition
    action_scope: Tuple[str, ...]        # actions observed (never prescribed)
    condition: Tuple[str, ...]           # frozen band/categorical clauses
    mechanism: str                       # INFERRED plain-language summary
    expected_failure_mode: str           # e.g. "adverse_MAE"
    observed_adverse_rate: float
    baseline_adverse_rate: float
    effect_delta: float
    forecast_evidence: Tuple[Tuple[str, str], ...]  # MODEL_DERIVED
    temporal_support: Tuple[Tuple[str, str], ...]   # per-split N/rate
    sample_count: int
    calibration: Tuple[Tuple[str, str], ...]
    model_metadata: Tuple[Tuple[str, str], ...]
    feature_provenance: Tuple[Tuple[str, str], ...]
    information_set_fingerprint: str
    provenance_class: str                # INFERRED (condition+effect)
    status: str = CANDIDATE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "target": self.target,
            "decision_scope": list(self.decision_scope),
            "instrument_scope": list(self.instrument_scope),
            "action_scope": list(self.action_scope),
            "condition": list(self.condition),
            "mechanism": self.mechanism,
            "expected_failure_mode": self.expected_failure_mode,
            "observed_adverse_rate": self.observed_adverse_rate,
            "baseline_adverse_rate": self.baseline_adverse_rate,
            "effect_delta": self.effect_delta,
            "forecast_evidence": [list(p) for p in self.forecast_evidence],
            "temporal_support": [list(p) for p in self.temporal_support],
            "sample_count": self.sample_count,
            "calibration": [list(p) for p in self.calibration],
            "model_metadata": [list(p) for p in self.model_metadata],
            "feature_provenance": [list(p) for p in self.feature_provenance],
            "information_set_fingerprint": self.information_set_fingerprint,
            "provenance_class": self.provenance_class,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]
                  ) -> "DiagnosticHypothesis":
        known = {"hypothesis_id", "target", "decision_scope",
                 "instrument_scope", "action_scope", "condition",
                 "mechanism", "expected_failure_mode",
                 "observed_adverse_rate", "baseline_adverse_rate",
                 "effect_delta", "forecast_evidence", "temporal_support",
                 "sample_count", "calibration", "model_metadata",
                 "feature_provenance", "information_set_fingerprint",
                 "provenance_class", "status"}
        unknown = set(payload) - known
        if unknown:
            raise ValueError(
                f"unknown DiagnosticHypothesis fields: {unknown}")
        for field in known - {"status"}:
            if field not in payload:
                raise ValueError(
                    f"missing DiagnosticHypothesis field: {field}")
        if payload.get("status", CANDIDATE) != CANDIDATE:
            raise ValueError(
                "DiagnosticHypothesis is born CANDIDATE; only validation "
                "may advance status, never construction")
        return cls(
            hypothesis_id=str(payload["hypothesis_id"]),
            target=str(payload["target"]),
            decision_scope=tuple(payload["decision_scope"]),
            instrument_scope=tuple(payload["instrument_scope"]),
            action_scope=tuple(payload["action_scope"]),
            condition=tuple(payload["condition"]),
            mechanism=str(payload["mechanism"]),
            expected_failure_mode=str(payload["expected_failure_mode"]),
            observed_adverse_rate=float(payload["observed_adverse_rate"]),
            baseline_adverse_rate=float(payload["baseline_adverse_rate"]),
            effect_delta=float(payload["effect_delta"]),
            forecast_evidence=tuple(tuple(p) for p in
                                    payload["forecast_evidence"]),
            temporal_support=tuple(tuple(p) for p in
                                   payload["temporal_support"]),
            sample_count=int(payload["sample_count"]),
            calibration=tuple(tuple(p) for p in payload["calibration"]),
            model_metadata=tuple(tuple(p) for p in
                                 payload["model_metadata"]),
            feature_provenance=tuple(tuple(p) for p in
                                     payload["feature_provenance"]),
            information_set_fingerprint=str(
                payload["information_set_fingerprint"]),
            provenance_class=str(payload["provenance_class"]),
            status=CANDIDATE,
        )
