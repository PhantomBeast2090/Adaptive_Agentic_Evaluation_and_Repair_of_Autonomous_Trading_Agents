"""Diagnostic proposals and selection rationales (E2-A).

``DiagnosticProposal`` is the schema-constrained output shape expected from
the future diagnostic agent: which hypotheses compete, which predictions
they staked, which test was selected and why, what discrimination is
expected, and which alternatives were passed over. ``SelectionRationale``
records the selector's reasoning per candidate so test choice stays
auditable without claiming optimal information gain.

Both reference other diagnostic objects by id — they never embed them.
Forming proposals and scoring candidates belongs to the future selector
(E2-B); this module is representation only. No LLM lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.contracts.fingerprints import fingerprint_of_dict


@dataclass(frozen=True)
class CandidateAssessment:
    """One candidate test as considered by the selector."""

    test_id: str
    expected_discrimination: str
    estimated_cost: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.test_id, str) or not self.test_id.strip():
            raise ValueError("test_id must be a non-empty string")
        if (
            not isinstance(self.expected_discrimination, str)
            or not self.expected_discrimination.strip()
        ):
            raise ValueError(
                "expected_discrimination must be a non-empty string"
            )
        if isinstance(self.estimated_cost, bool) or not isinstance(
            self.estimated_cost, (int, float)
        ):
            raise TypeError("estimated_cost must be a finite number")
        if self.estimated_cost != self.estimated_cost or self.estimated_cost in (
            float("inf"),
            float("-inf"),
        ):
            raise ValueError("estimated_cost must be a finite number")
        if float(self.estimated_cost) < 0:
            raise ValueError("estimated_cost must be non-negative")
        object.__setattr__(self, "estimated_cost", float(self.estimated_cost))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "expected_discrimination": self.expected_discrimination,
            "estimated_cost": self.estimated_cost,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CandidateAssessment":
        if not isinstance(payload, Mapping):
            raise TypeError("CandidateAssessment payload must be a mapping")
        known = {"test_id", "expected_discrimination", "estimated_cost"}
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown CandidateAssessment fields: {sorted(extra)}"
            )
        try:
            return cls(
                test_id=payload["test_id"],
                expected_discrimination=payload["expected_discrimination"],
                estimated_cost=payload.get("estimated_cost", 0.0),
            )
        except KeyError as exc:
            raise ValueError(
                f"CandidateAssessment payload missing {exc}"
            ) from exc


@dataclass(frozen=True)
class SelectionRationale:
    """Why the selector chose one test over the considered alternatives."""

    rationale_id: str
    candidates: Tuple[CandidateAssessment, ...] = field(default_factory=tuple)
    selected_test_id: str = ""
    selection_score: Optional[float] = None
    method: str = ""
    version: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.rationale_id, str) or not self.rationale_id.strip():
            raise ValueError("rationale_id must be a non-empty string")
        candidates = self.candidates
        if isinstance(candidates, str) or not isinstance(
            candidates, (tuple, list)
        ):
            raise TypeError(
                "candidates must be a tuple/list of CandidateAssessment"
            )
        candidates = tuple(candidates)
        if not candidates:
            raise ValueError("candidates must be non-empty")
        for candidate in candidates:
            if not isinstance(candidate, CandidateAssessment):
                raise TypeError(
                    "candidates must contain CandidateAssessment, "
                    f"got {type(candidate).__name__}"
                )
        ids = [candidate.test_id for candidate in candidates]
        if len(set(ids)) != len(ids):
            raise ValueError("candidate test_ids must not contain duplicates")
        object.__setattr__(self, "candidates", candidates)
        if (
            not isinstance(self.selected_test_id, str)
            or not self.selected_test_id.strip()
        ):
            raise ValueError("selected_test_id must be a non-empty string")
        if self.selected_test_id not in ids:
            raise ValueError(
                "selected_test_id must be one of the considered candidates"
            )
        if self.selection_score is not None:
            if (
                not isinstance(self.selection_score, (int, float))
                or isinstance(self.selection_score, bool)
                or self.selection_score != self.selection_score
                or self.selection_score in (float("inf"), float("-inf"))
            ):
                raise ValueError(
                    "selection_score must be a finite number or None "
                    "(None records that no score was computed)"
                )
            object.__setattr__(
                self, "selection_score", float(self.selection_score)
            )
        for field_name in ("method", "version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string "
                    "(selection without a named method is not auditable)"
                )

    def candidate(self, test_id: str) -> CandidateAssessment:
        """Fetch one considered candidate by test id."""
        for candidate in self.candidates:
            if candidate.test_id == test_id:
                return candidate
        raise KeyError(f"no candidate {test_id!r} was considered")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rationale_id": self.rationale_id,
            "candidates": [c.to_dict() for c in self.candidates],
            "selected_test_id": self.selected_test_id,
            "selection_score": self.selection_score,
            "method": self.method,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SelectionRationale":
        if not isinstance(payload, Mapping):
            raise TypeError("SelectionRationale payload must be a mapping")
        known = {
            "rationale_id", "candidates", "selected_test_id",
            "selection_score", "method", "version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown SelectionRationale fields: {sorted(extra)}"
            )
        try:
            return cls(
                rationale_id=payload["rationale_id"],
                candidates=tuple(
                    CandidateAssessment.from_dict(item)
                    for item in payload.get("candidates", ())
                ),
                selected_test_id=payload["selected_test_id"],
                selection_score=payload.get("selection_score"),
                method=payload["method"],
                version=payload["version"],
            )
        except KeyError as exc:
            raise ValueError(
                f"SelectionRationale payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        """Deterministic identity over every rationale field."""
        return fingerprint_of_dict(self.to_dict())


@dataclass(frozen=True)
class DiagnosticProposal:
    """Schema-constrained output shape for the future diagnostic agent."""

    proposal_id: str
    hypothesis_ids: Tuple[str, ...] = field(default_factory=tuple)
    prediction_ids: Tuple[str, ...] = field(default_factory=tuple)
    selected_test_id: str = ""
    expected_discrimination: str = ""
    rationale_id: str = ""
    confidence: float = 0.0
    alternative_test_ids: Tuple[str, ...] = field(default_factory=tuple)
    method: str = ""
    version: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.proposal_id, str) or not self.proposal_id.strip():
            raise ValueError("proposal_id must be a non-empty string")
        object.__setattr__(
            self, "hypothesis_ids",
            self._checked_id_tuple(self.hypothesis_ids, "hypothesis_ids"),
        )
        if not self.hypothesis_ids:
            raise ValueError("hypothesis_ids must be non-empty")
        object.__setattr__(
            self, "prediction_ids",
            self._checked_id_tuple(self.prediction_ids, "prediction_ids"),
        )
        if (
            not isinstance(self.selected_test_id, str)
            or not self.selected_test_id.strip()
        ):
            raise ValueError("selected_test_id must be a non-empty string")
        if (
            not isinstance(self.expected_discrimination, str)
            or not self.expected_discrimination.strip()
        ):
            raise ValueError(
                "expected_discrimination must be a non-empty string"
            )
        if not isinstance(self.rationale_id, str) or not self.rationale_id.strip():
            raise ValueError("rationale_id must be a non-empty string")
        if (
            not isinstance(self.confidence, (int, float))
            or isinstance(self.confidence, bool)
            or not 0.0 <= float(self.confidence) <= 1.0
        ):
            raise ValueError("confidence must be in [0, 1]")
        object.__setattr__(self, "confidence", float(self.confidence))
        alternatives = self._checked_id_tuple(
            self.alternative_test_ids, "alternative_test_ids"
        )
        if self.selected_test_id in alternatives:
            raise ValueError(
                "selected_test_id must not appear among alternative_test_ids"
            )
        object.__setattr__(self, "alternative_test_ids", alternatives)
        for field_name in ("method", "version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )

    @staticmethod
    def _checked_id_tuple(value: object, field_name: str) -> Tuple[str, ...]:
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "hypothesis_ids": list(self.hypothesis_ids),
            "prediction_ids": list(self.prediction_ids),
            "selected_test_id": self.selected_test_id,
            "expected_discrimination": self.expected_discrimination,
            "rationale_id": self.rationale_id,
            "confidence": self.confidence,
            "alternative_test_ids": list(self.alternative_test_ids),
            "method": self.method,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DiagnosticProposal":
        if not isinstance(payload, Mapping):
            raise TypeError("DiagnosticProposal payload must be a mapping")
        known = {
            "proposal_id", "hypothesis_ids", "prediction_ids",
            "selected_test_id", "expected_discrimination", "rationale_id",
            "confidence", "alternative_test_ids", "method", "version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown DiagnosticProposal fields: {sorted(extra)}"
            )
        try:
            return cls(
                proposal_id=payload["proposal_id"],
                hypothesis_ids=tuple(payload.get("hypothesis_ids", ())),
                prediction_ids=tuple(payload.get("prediction_ids", ())),
                selected_test_id=payload["selected_test_id"],
                expected_discrimination=payload["expected_discrimination"],
                rationale_id=payload["rationale_id"],
                confidence=payload.get("confidence", 0.0),
                alternative_test_ids=tuple(
                    payload.get("alternative_test_ids", ())
                ),
                method=payload["method"],
                version=payload["version"],
            )
        except KeyError as exc:
            raise ValueError(
                f"DiagnosticProposal payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        """Deterministic identity over every proposal field."""
        return fingerprint_of_dict(self.to_dict())
