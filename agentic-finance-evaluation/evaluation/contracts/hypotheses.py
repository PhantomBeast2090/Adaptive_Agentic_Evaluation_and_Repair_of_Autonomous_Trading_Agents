"""Hypothesis: structured competing failure-mechanism claims (E0 contract).

Core research principle enforced here: **observed failure is not proven
mechanism**. High turnover is a behavioral symptom; "overreaction to
short-lived price movements" is one candidate mechanism among several.
The contract therefore:

* separates ``failure_class`` (what was observed) from ``mechanism``
  (why it might have happened) and rejects records where the two are
  identical;
* supports multiple competing hypotheses over the same evidence
  (``alternative_hypotheses`` names the rivals; nothing enforces a single
  explanation);
* tracks lifecycle via ``HypothesisStatus`` (PROPOSED/SUPPORTED/WEAKENED/
  REJECTED/UNRESOLVED) with pure ``with_status`` transitions (hypotheses
  are frozen; status changes produce new instances);
* grounds every non-proposed hypothesis in evidence fingerprints and
  names the discriminating tests that could separate it from its rivals.

E0 defines the representation only. Hypothesis *formation*, scoring, and
adaptive test selection are E2 work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Tuple

from evaluation.contracts.fingerprints import fingerprint_of_dict


class HypothesisStatus(str, Enum):
    """Closed lifecycle vocabulary for one hypothesis."""

    PROPOSED = "PROPOSED"
    SUPPORTED = "SUPPORTED"
    WEAKENED = "WEAKENED"
    REJECTED = "REJECTED"
    UNRESOLVED = "UNRESOLVED"

    def to_str(self) -> str:
        return self.value

    @classmethod
    def from_str(cls, value: object) -> "HypothesisStatus":
        for member in cls:
            if value == member.value:
                return member
        known = sorted(member.value for member in cls)
        raise ValueError(f"unknown HypothesisStatus {value!r}; known: {known}")


@dataclass(frozen=True)
class Hypothesis:
    """One structured, falsifiable failure-mechanism claim."""

    hypothesis_id: str
    failure_class: str
    mechanism: str
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 0.0
    alternative_hypotheses: Tuple[str, ...] = field(default_factory=tuple)
    discriminating_tests: Tuple[str, ...] = field(default_factory=tuple)
    status: HypothesisStatus = HypothesisStatus.PROPOSED

    def __post_init__(self) -> None:
        if (
            not isinstance(self.hypothesis_id, str)
            or not self.hypothesis_id.strip()
        ):
            raise ValueError("hypothesis_id must be a non-empty string")
        if (
            not isinstance(self.failure_class, str)
            or not self.failure_class.strip()
        ):
            raise ValueError("failure_class must be a non-empty string")
        if not isinstance(self.mechanism, str) or not self.mechanism.strip():
            raise ValueError("mechanism must be a non-empty string")
        if self.mechanism.strip().lower() == self.failure_class.strip().lower():
            raise ValueError(
                "mechanism must explain the failure_class, not restate it: "
                "observed failure is not proven mechanism"
            )
        status = self.status
        if isinstance(status, str) and not isinstance(status, HypothesisStatus):
            status = HypothesisStatus.from_str(status)
        if not isinstance(status, HypothesisStatus):
            raise TypeError(
                "status must be a HypothesisStatus member, "
                f"got {self.status!r}"
            )
        object.__setattr__(self, "status", status)
        refs = self._checked_str_tuple(self.evidence_refs, "evidence_refs")
        if status is not HypothesisStatus.PROPOSED and not refs:
            raise ValueError(
                "only PROPOSED hypotheses may carry empty evidence_refs; "
                "a status claim must be grounded in evidence"
            )
        object.__setattr__(self, "evidence_refs", refs)
        if (
            not isinstance(self.confidence, (int, float))
            or isinstance(self.confidence, bool)
            or not 0.0 <= float(self.confidence) <= 1.0
        ):
            raise ValueError("confidence must be in [0, 1]")
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(
            self, "alternative_hypotheses",
            self._checked_str_tuple(
                self.alternative_hypotheses, "alternative_hypotheses"
            ),
        )
        object.__setattr__(
            self, "discriminating_tests",
            self._checked_str_tuple(
                self.discriminating_tests, "discriminating_tests"
            ),
        )

    @staticmethod
    def _checked_str_tuple(value: object, field_name: str) -> Tuple[str, ...]:
        if isinstance(value, str) or not isinstance(value, (tuple, list)):
            raise TypeError(f"{field_name} must be a tuple/list of strings")
        items = tuple(value)
        for item in items:
            if not isinstance(item, str) or not item:
                raise ValueError(
                    f"{field_name} entries must be non-empty strings"
                )
        if len(set(items)) != len(items):
            raise ValueError(f"{field_name} must not contain duplicates")
        return items

    def with_status(self, status: HypothesisStatus | str) -> "Hypothesis":
        """Return a copy of this hypothesis at a new lifecycle status."""
        if isinstance(status, str) and not isinstance(status, HypothesisStatus):
            status = HypothesisStatus.from_str(status)
        if not isinstance(status, HypothesisStatus):
            raise TypeError(
                f"status must be a HypothesisStatus, got {status!r}"
            )
        return Hypothesis(
            hypothesis_id=self.hypothesis_id,
            failure_class=self.failure_class,
            mechanism=self.mechanism,
            evidence_refs=self.evidence_refs,
            confidence=self.confidence,
            alternative_hypotheses=self.alternative_hypotheses,
            discriminating_tests=self.discriminating_tests,
            status=status,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "failure_class": self.failure_class,
            "mechanism": self.mechanism,
            "evidence_refs": list(self.evidence_refs),
            "confidence": self.confidence,
            "alternative_hypotheses": list(self.alternative_hypotheses),
            "discriminating_tests": list(self.discriminating_tests),
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Hypothesis":
        if not isinstance(payload, Mapping):
            raise TypeError("Hypothesis payload must be a mapping")
        known = {
            "hypothesis_id", "failure_class", "mechanism", "evidence_refs",
            "confidence", "alternative_hypotheses", "discriminating_tests",
            "status",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(f"unknown Hypothesis fields: {sorted(extra)}")
        try:
            return cls(
                hypothesis_id=payload["hypothesis_id"],
                failure_class=payload["failure_class"],
                mechanism=payload["mechanism"],
                evidence_refs=tuple(payload.get("evidence_refs", ())),
                confidence=payload.get("confidence", 0.0),
                alternative_hypotheses=tuple(
                    payload.get("alternative_hypotheses", ())
                ),
                discriminating_tests=tuple(
                    payload.get("discriminating_tests", ())
                ),
                status=payload.get("status", HypothesisStatus.PROPOSED),
            )
        except KeyError as exc:
            raise ValueError(f"Hypothesis payload missing {exc}") from exc

    def fingerprint(self) -> str:
        """Deterministic identity over every hypothesis field."""
        return fingerprint_of_dict(self.to_dict())
