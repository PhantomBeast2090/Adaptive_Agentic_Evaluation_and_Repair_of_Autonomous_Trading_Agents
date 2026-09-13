"""BehavioralEvidence: derived/evaluated evidence (E0 contract).

Conceptual split enforced by this layer::

    DecisionRecord(s)   = raw observable events (what happened)
            |
            v
    EvidenceCollector   = deterministic derivation (E1, not E0)
            |
            v
    BehavioralEvidence  = derived claim about behavior (this module)
            |
            v
    DiagnosticReasoning = competing hypotheses (E2, not E0)

A ``BehavioralEvidence`` item is therefore always *derived*: it names the
decision records it was computed from (by fingerprint), the derivation
method and producer version, and a closed category. Raw records and
derived claims are different types and are never interchangeable.

E0 defines the representation only. The metric/derivation engine that
*produces* evidence is E1 work.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.contracts.fingerprints import fingerprint_of_dict, freeze, thaw


class EvidenceCategory(str, Enum):
    """Closed vocabulary of behavioral evidence categories."""

    RISK = "RISK"
    TEMPORAL = "TEMPORAL"
    MARKET_REGIME = "MARKET_REGIME"
    DECISION_BEHAVIOR = "DECISION_BEHAVIOR"
    INFORMATION_USAGE = "INFORMATION_USAGE"
    ROBUSTNESS = "ROBUSTNESS"
    EXECUTION = "EXECUTION"

    def to_str(self) -> str:
        return self.value

    @classmethod
    def from_str(cls, value: object) -> "EvidenceCategory":
        for member in cls:
            if value == member.value:
                return member
        known = sorted(member.value for member in cls)
        raise ValueError(f"unknown EvidenceCategory {value!r}; known: {known}")


@dataclass(frozen=True)
class BehavioralEvidence:
    """One derived, categorized unit of behavioral evidence."""

    evidence_id: str
    category: EvidenceCategory
    metric_name: str
    value: Optional[float] = None
    value_absent_reason: Optional[str] = None
    decision_refs: Tuple[str, ...] = field(default_factory=tuple)
    derivation: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    severity: Optional[str] = None
    confidence: Optional[float] = None
    provenance: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_id, str) or not self.evidence_id.strip():
            raise ValueError("evidence_id must be a non-empty string")
        category = self.category
        if isinstance(category, str) and not isinstance(category, EvidenceCategory):
            category = EvidenceCategory.from_str(category)
        if not isinstance(category, EvidenceCategory):
            raise TypeError(
                "category must be an EvidenceCategory member, "
                f"got {self.category!r}"
            )
        object.__setattr__(self, "category", category)
        if not isinstance(self.metric_name, str) or not self.metric_name.strip():
            raise ValueError("metric_name must be a non-empty string")
        if self.value is None:
            if (
                not isinstance(self.value_absent_reason, str)
                or not self.value_absent_reason.strip()
            ):
                raise ValueError(
                    "value=None requires a non-empty value_absent_reason "
                    "(undefined metrics are explicit, never silent)"
                )
        else:
            if (
                not isinstance(self.value, (int, float))
                or isinstance(self.value, bool)
                or self.value != self.value
                or self.value in (float("inf"), float("-inf"))
            ):
                raise ValueError("value must be a finite number or None")
            object.__setattr__(self, "value", float(self.value))
            if self.value_absent_reason is not None:
                raise ValueError(
                    "value_absent_reason must be None when value is present"
                )
        refs = self.decision_refs
        if isinstance(refs, str) or not isinstance(refs, (tuple, list)):
            raise TypeError("decision_refs must be a tuple/list of fingerprints")
        refs = tuple(refs)
        if not refs:
            raise ValueError("decision_refs must be non-empty")
        for ref in refs:
            if not isinstance(ref, str) or not ref:
                raise ValueError("decision_refs entries must be non-empty strings")
        if len(set(refs)) != len(refs):
            raise ValueError("decision_refs must not contain duplicates")
        object.__setattr__(self, "decision_refs", refs)
        derivation = self._checked_mapping(
            self.derivation, "derivation", required_keys=("method",)
        )
        if not isinstance(derivation["method"], str) or not derivation["method"]:
            raise ValueError("derivation['method'] must be a non-empty string")
        object.__setattr__(self, "derivation", freeze(derivation))
        if self.severity is not None and (
            not isinstance(self.severity, str) or not self.severity
        ):
            raise ValueError("severity must be a non-empty string or None")
        if self.confidence is not None:
            if (
                not isinstance(self.confidence, (int, float))
                or isinstance(self.confidence, bool)
                or not 0.0 <= float(self.confidence) <= 1.0
            ):
                raise ValueError("confidence must be in [0, 1] or None")
            object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(
            self, "provenance",
            freeze(self._checked_mapping(self.provenance, "provenance")),
        )

    @staticmethod
    def _checked_mapping(
        value: object, field_name: str, required_keys: Tuple[str, ...] = ()
    ) -> Dict[str, Any]:
        if not isinstance(value, Mapping):
            raise TypeError(f"{field_name} must be a mapping")
        mapping = dict(value)
        for key in required_keys:
            if key not in mapping:
                raise ValueError(f"{field_name} must carry {key!r}")
        return mapping

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "category": self.category.value,
            "metric_name": self.metric_name,
            "value": self.value,
            "value_absent_reason": self.value_absent_reason,
            "decision_refs": list(self.decision_refs),
            "derivation": thaw(self.derivation),
            "severity": self.severity,
            "confidence": self.confidence,
            "provenance": thaw(self.provenance),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BehavioralEvidence":
        if not isinstance(payload, Mapping):
            raise TypeError("BehavioralEvidence payload must be a mapping")
        known = {
            "evidence_id", "category", "metric_name", "value",
            "value_absent_reason", "decision_refs", "derivation",
            "severity", "confidence", "provenance",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown BehavioralEvidence fields: {sorted(extra)}"
            )
        try:
            return cls(
                evidence_id=payload["evidence_id"],
                category=payload["category"],
                metric_name=payload["metric_name"],
                value=payload.get("value"),
                value_absent_reason=payload.get("value_absent_reason"),
                decision_refs=tuple(payload.get("decision_refs", ())),
                derivation=dict(payload.get("derivation", {})),
                severity=payload.get("severity"),
                confidence=payload.get("confidence"),
                provenance=dict(payload.get("provenance", {})),
            )
        except KeyError as exc:
            raise ValueError(
                f"BehavioralEvidence payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        """Deterministic identity over every evidence field."""
        return fingerprint_of_dict(self.to_dict())
