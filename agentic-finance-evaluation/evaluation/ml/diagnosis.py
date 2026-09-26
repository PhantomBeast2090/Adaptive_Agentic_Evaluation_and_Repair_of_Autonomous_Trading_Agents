"""FailureHypothesis: evaluator-side suspicion, not knowledge.

A FailureHypothesis records "the model suspects this environmental
condition is associated with failure". It is NOT validated knowledge:
it must still pass extraction conventions, validation, admission, and
MemoryStore before it can ever become a LearnedContext. This module
creates hypotheses only; it never writes to MemoryStore.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple


@dataclass(frozen=True)
class FailureHypothesis:
    """One model-suspected decision failure with full provenance."""

    decision_id: str
    experiment_id: str
    decision_timestamp: str
    target: str
    predicted_adverse_probability: float
    observed_target: Optional[bool]
    top_contributing_features: Tuple[str, ...]
    model_metadata: Tuple[Tuple[str, str], ...]
    calibration_metadata: Tuple[Tuple[str, str], ...]
    feature_schema_hash: str
    training_fingerprint: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "experiment_id": self.experiment_id,
            "decision_timestamp": self.decision_timestamp,
            "target": self.target,
            "predicted_adverse_probability":
                self.predicted_adverse_probability,
            "observed_target": self.observed_target,
            "top_contributing_features": list(
                self.top_contributing_features),
            "model_metadata": [list(p) for p in self.model_metadata],
            "calibration_metadata": [list(p) for p in
                                     self.calibration_metadata],
            "feature_schema_hash": self.feature_schema_hash,
            "training_fingerprint": self.training_fingerprint,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FailureHypothesis":
        known = {"decision_id", "experiment_id", "decision_timestamp",
                 "target", "predicted_adverse_probability",
                 "observed_target", "top_contributing_features",
                 "model_metadata", "calibration_metadata",
                 "feature_schema_hash", "training_fingerprint"}
        unknown = set(payload) - known
        if unknown:
            raise ValueError(f"unknown FailureHypothesis fields: {unknown}")
        for field in known:
            if field not in payload:
                raise ValueError(f"missing FailureHypothesis field: {field}")
        return cls(
            decision_id=str(payload["decision_id"]),
            experiment_id=str(payload["experiment_id"]),
            decision_timestamp=str(payload["decision_timestamp"]),
            target=str(payload["target"]),
            predicted_adverse_probability=float(
                payload["predicted_adverse_probability"]),
            observed_target=(None if payload["observed_target"] is None
                             else bool(payload["observed_target"])),
            top_contributing_features=tuple(
                payload["top_contributing_features"]),
            model_metadata=tuple(tuple(p) for p in
                                 payload["model_metadata"]),
            calibration_metadata=tuple(tuple(p) for p in
                                       payload["calibration_metadata"]),
            feature_schema_hash=str(payload["feature_schema_hash"]),
            training_fingerprint=str(payload["training_fingerprint"]),
        )
