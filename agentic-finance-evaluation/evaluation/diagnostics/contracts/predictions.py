"""Committed hypothesis predictions for adaptive diagnosis (E2-A).

A ``HypothesisPrediction`` is a falsifiable claim staked by one hypothesis
about one diagnostic test, committed BEFORE the test executes. The future
diagnostic loop commits rival predictions on the same test so outcomes can
discriminate between mechanisms rather than merely confirm one story.

One prediction per (hypothesis, test) pair: re-predicting the same pair is
rejected so goalposts cannot move after seeing outcomes. Predictions are
frozen dataclasses — immutable after creation by construction.

No inference lives here. Formation of predictions belongs to the future
diagnostic agent (E2-B); this module is representation only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Mapping

from evaluation.contracts.fingerprints import fingerprint_of_dict


class ExpectedDirection(str, Enum):
    """Closed vocabulary for the predicted direction of an observable."""

    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    NO_CHANGE = "NO_CHANGE"

    def to_str(self) -> str:
        return self.value

    @classmethod
    def from_str(cls, value: object) -> "ExpectedDirection":
        for member in cls:
            if value == member.value:
                return member
        known = sorted(member.value for member in cls)
        raise ValueError(
            f"unknown ExpectedDirection {value!r}; known: {known}"
        )


@dataclass(frozen=True)
class HypothesisPrediction:
    """One committed prediction of one hypothesis about one test."""

    prediction_id: str
    hypothesis_id: str
    test_id: str
    predicted_observable: str
    expected_direction: ExpectedDirection
    expected_magnitude: str | None = None
    confidence: float = 0.0
    rationale: str = ""
    derivation_method: str = ""
    derivation_version: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "prediction_id",
            "hypothesis_id",
            "test_id",
            "predicted_observable",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        direction = self.expected_direction
        if isinstance(direction, str) and not isinstance(
            direction, ExpectedDirection
        ):
            direction = ExpectedDirection.from_str(direction)
        if not isinstance(direction, ExpectedDirection):
            raise TypeError(
                "expected_direction must be an ExpectedDirection member, "
                f"got {self.expected_direction!r}"
            )
        object.__setattr__(self, "expected_direction", direction)
        if self.expected_magnitude is not None and (
            not isinstance(self.expected_magnitude, str)
            or not self.expected_magnitude.strip()
        ):
            raise ValueError(
                "expected_magnitude must be a non-empty string or None"
            )
        if (
            not isinstance(self.confidence, (int, float))
            or isinstance(self.confidence, bool)
            or not 0.0 <= float(self.confidence) <= 1.0
        ):
            raise ValueError("confidence must be in [0, 1]")
        object.__setattr__(self, "confidence", float(self.confidence))
        if not isinstance(self.rationale, str) or not self.rationale.strip():
            raise ValueError("rationale must be a non-empty string")
        for field_name in ("derivation_method", "derivation_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string "
                    "(predictions carry their provenance)"
                )

    def pair(self) -> tuple[str, str]:
        """The (hypothesis_id, test_id) pair this prediction commits."""
        return (self.hypothesis_id, self.test_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "hypothesis_id": self.hypothesis_id,
            "test_id": self.test_id,
            "predicted_observable": self.predicted_observable,
            "expected_direction": self.expected_direction.value,
            "expected_magnitude": self.expected_magnitude,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "derivation_method": self.derivation_method,
            "derivation_version": self.derivation_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HypothesisPrediction":
        if not isinstance(payload, Mapping):
            raise TypeError("HypothesisPrediction payload must be a mapping")
        known = {
            "prediction_id", "hypothesis_id", "test_id",
            "predicted_observable", "expected_direction",
            "expected_magnitude", "confidence", "rationale",
            "derivation_method", "derivation_version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown HypothesisPrediction fields: {sorted(extra)}"
            )
        try:
            return cls(
                prediction_id=payload["prediction_id"],
                hypothesis_id=payload["hypothesis_id"],
                test_id=payload["test_id"],
                predicted_observable=payload["predicted_observable"],
                expected_direction=payload["expected_direction"],
                expected_magnitude=payload.get("expected_magnitude"),
                confidence=payload.get("confidence", 0.0),
                rationale=payload["rationale"],
                derivation_method=payload["derivation_method"],
                derivation_version=payload["derivation_version"],
            )
        except KeyError as exc:
            raise ValueError(
                f"HypothesisPrediction payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        """Deterministic identity over every prediction field."""
        return fingerprint_of_dict(self.to_dict())
