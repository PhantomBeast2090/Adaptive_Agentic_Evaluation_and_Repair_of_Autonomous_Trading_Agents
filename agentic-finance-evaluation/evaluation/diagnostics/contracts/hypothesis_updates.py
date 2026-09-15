"""Hypothesis updates for adaptive diagnosis (E2-A).

A ``HypothesisUpdate`` records one assessed encounter between a committed
prediction and an executed result: what the hypothesis claimed, what the
test observed, whether the two are compatible, and what the hypothesis
becomes. The prior hypothesis is preserved in full — updates append, they
never rewrite history.

Confidence here is a recorded judgement, NOT a Bayesian posterior. No
inference machinery ships in E2-A, so the update ``method`` must name the
actual assessment procedure (e.g. a named heuristic rule with a version),
and must not claim Bayesian updating it does not perform.

Applying updates (the loop) belongs to the future diagnostic runner
(E2-B); this module is representation only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Mapping, Tuple

from evaluation.contracts.fingerprints import fingerprint_of_dict
from evaluation.contracts.hypotheses import Hypothesis


class Compatibility(str, Enum):
    """Closed vocabulary for prediction-vs-observation assessment."""

    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    INCONCLUSIVE = "INCONCLUSIVE"

    def to_str(self) -> str:
        return self.value

    @classmethod
    def from_str(cls, value: object) -> "Compatibility":
        for member in cls:
            if value == member.value:
                return member
        known = sorted(member.value for member in cls)
        raise ValueError(f"unknown Compatibility {value!r}; known: {known}")


@dataclass(frozen=True)
class HypothesisUpdate:
    """One assessed prediction/result encounter for one hypothesis."""

    update_id: str
    hypothesis_id: str
    prior: Hypothesis
    prior_fingerprint: str
    prediction_id: str
    result_id: str
    compatibility: Compatibility
    assessment: str
    updated: Hypothesis
    updated_confidence: float = 0.0
    evidence_refs: Tuple[str, ...] = ()
    method: str = ""
    version: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "update_id",
            "hypothesis_id",
            "prediction_id",
            "result_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        if not isinstance(self.prior, Hypothesis):
            raise TypeError(
                f"prior must be a Hypothesis, got {type(self.prior).__name__}"
            )
        if (
            not isinstance(self.prior_fingerprint, str)
            or not self.prior_fingerprint.strip()
        ):
            raise ValueError("prior_fingerprint must be a non-empty string")
        if self.prior_fingerprint != self.prior.fingerprint():
            raise ValueError(
                "prior_fingerprint must equal prior.fingerprint(): "
                "the preserved prior must be exactly the assessed one"
            )
        if self.prior.hypothesis_id != self.hypothesis_id:
            raise ValueError(
                "prior.hypothesis_id must match the update's hypothesis_id"
            )
        compatibility = self.compatibility
        if isinstance(compatibility, str) and not isinstance(
            compatibility, Compatibility
        ):
            compatibility = Compatibility.from_str(compatibility)
        if not isinstance(compatibility, Compatibility):
            raise TypeError(
                "compatibility must be a Compatibility member, "
                f"got {self.compatibility!r}"
            )
        object.__setattr__(self, "compatibility", compatibility)
        if not isinstance(self.assessment, str) or not self.assessment.strip():
            raise ValueError("assessment must be a non-empty string")
        if not isinstance(self.updated, Hypothesis):
            raise TypeError(
                "updated must be a Hypothesis, "
                f"got {type(self.updated).__name__}"
            )
        if self.updated.hypothesis_id != self.hypothesis_id:
            raise ValueError(
                "updated.hypothesis_id must match the update's hypothesis_id"
            )
        if (
            not isinstance(self.updated_confidence, (int, float))
            or isinstance(self.updated_confidence, bool)
            or not 0.0 <= float(self.updated_confidence) <= 1.0
        ):
            raise ValueError("updated_confidence must be in [0, 1]")
        object.__setattr__(
            self, "updated_confidence", float(self.updated_confidence)
        )
        if abs(self.updated.confidence - self.updated_confidence) > 1e-12:
            raise ValueError(
                "updated.confidence must equal updated_confidence: "
                "the recorded judgement lives in exactly one place"
            )
        refs = self.evidence_refs
        if isinstance(refs, str) or not isinstance(refs, (tuple, list)):
            raise TypeError("evidence_refs must be a tuple/list of strings")
        refs = tuple(refs)
        for ref in refs:
            if not isinstance(ref, str) or not ref:
                raise ValueError(
                    "evidence_refs entries must be non-empty strings"
                )
        if len(set(refs)) != len(refs):
            raise ValueError("evidence_refs must not contain duplicates")
        object.__setattr__(self, "evidence_refs", refs)
        for field_name in ("method", "version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string "
                    "(updates carry their procedure, never a bare number)"
                )
        lowered = f"{self.method} {self.version}".lower()
        if "bayes" in lowered or "posterior" in lowered:
            raise ValueError(
                "update method must not claim Bayesian/posterior inference: "
                "E2-A ships no Bayesian machinery"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "update_id": self.update_id,
            "hypothesis_id": self.hypothesis_id,
            "prior": self.prior.to_dict(),
            "prior_fingerprint": self.prior_fingerprint,
            "prediction_id": self.prediction_id,
            "result_id": self.result_id,
            "compatibility": self.compatibility.value,
            "assessment": self.assessment,
            "updated": self.updated.to_dict(),
            "updated_confidence": self.updated_confidence,
            "evidence_refs": list(self.evidence_refs),
            "method": self.method,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HypothesisUpdate":
        if not isinstance(payload, Mapping):
            raise TypeError("HypothesisUpdate payload must be a mapping")
        known = {
            "update_id", "hypothesis_id", "prior", "prior_fingerprint",
            "prediction_id", "result_id", "compatibility", "assessment",
            "updated", "updated_confidence", "evidence_refs", "method",
            "version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown HypothesisUpdate fields: {sorted(extra)}"
            )
        try:
            return cls(
                update_id=payload["update_id"],
                hypothesis_id=payload["hypothesis_id"],
                prior=Hypothesis.from_dict(payload["prior"]),
                prior_fingerprint=payload["prior_fingerprint"],
                prediction_id=payload["prediction_id"],
                result_id=payload["result_id"],
                compatibility=payload["compatibility"],
                assessment=payload["assessment"],
                updated=Hypothesis.from_dict(payload["updated"]),
                updated_confidence=payload.get("updated_confidence", 0.0),
                evidence_refs=tuple(payload.get("evidence_refs", ())),
                method=payload["method"],
                version=payload["version"],
            )
        except KeyError as exc:
            raise ValueError(
                f"HypothesisUpdate payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        """Deterministic identity over every update field."""
        return fingerprint_of_dict(self.to_dict())
