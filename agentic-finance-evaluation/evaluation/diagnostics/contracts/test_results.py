"""Diagnostic test results (E2-A).

A ``DiagnosticTestResult`` records what one executed diagnostic test
observed — never what it means. Meaning (compatibility with committed
predictions) belongs to ``HypothesisUpdate``; this module carries the raw
adjudicating material:

* which test ran and which intervention fingerprint it ran under;
* which baseline it discriminates against (reference by identity only —
  baseline records are never copied here and can never be overwritten);
* the diagnostic episode's own record/evidence references (its own
  trajectory identity, separate from baseline);
* measured outcomes as E1 ``MetricResult`` items (reused, not duplicated);
* which committed predictions this result adjudicates;
* typed execution status with an E0-compatible ``outcome`` string so the
  result flows unchanged into ``EvaluationState.record_test_result``;
* failure information when execution did not complete;
* provenance and a deterministic fingerprint over everything.

No execution logic lives here. Running interventions belongs to the future
executor (E2-B); this module is representation only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.baseline.metrics import MetricResult
from evaluation.contracts.fingerprints import fingerprint_of_dict


class DiagnosticExecutionStatus(str, Enum):
    """Closed vocabulary for how a diagnostic test execution ended."""

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INVALID = "INVALID"

    def to_str(self) -> str:
        return self.value

    @classmethod
    def from_str(cls, value: object) -> "DiagnosticExecutionStatus":
        for member in cls:
            if value == member.value:
                return member
        known = sorted(member.value for member in cls)
        raise ValueError(
            f"unknown DiagnosticExecutionStatus {value!r}; known: {known}"
        )


@dataclass(frozen=True)
class DiagnosticTestResult:
    """One immutable record of one executed diagnostic test."""

    result_id: str
    test_id: str
    execution_fingerprint: str
    baseline_evaluation_id: str
    baseline_fingerprint: str
    intervention_fingerprint: str
    record_fps: Tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    measured: Tuple[MetricResult, ...] = field(default_factory=tuple)
    prediction_ids: Tuple[str, ...] = field(default_factory=tuple)
    status: DiagnosticExecutionStatus = DiagnosticExecutionStatus.COMPLETED
    error: Optional[str] = None
    provenance_method: str = ""
    provenance_version: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "result_id",
            "test_id",
            "execution_fingerprint",
            "baseline_evaluation_id",
            "baseline_fingerprint",
            "intervention_fingerprint",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        object.__setattr__(
            self, "record_fps",
            self._checked_ref_tuple(self.record_fps, "record_fps"),
        )
        object.__setattr__(
            self, "evidence_refs",
            self._checked_ref_tuple(self.evidence_refs, "evidence_refs"),
        )
        measured = self.measured
        if isinstance(measured, str) or not isinstance(measured, (tuple, list)):
            raise TypeError("measured must be a tuple/list of MetricResult")
        measured = tuple(measured)
        for item in measured:
            if not isinstance(item, MetricResult):
                raise TypeError(
                    "measured must contain MetricResult, "
                    f"got {type(item).__name__}"
                )
        object.__setattr__(self, "measured", measured)
        object.__setattr__(
            self, "prediction_ids",
            self._checked_ref_tuple(self.prediction_ids, "prediction_ids"),
        )
        status = self.status
        if isinstance(status, str) and not isinstance(
            status, DiagnosticExecutionStatus
        ):
            status = DiagnosticExecutionStatus.from_str(status)
        if not isinstance(status, DiagnosticExecutionStatus):
            raise TypeError(
                "status must be a DiagnosticExecutionStatus member, "
                f"got {self.status!r}"
            )
        object.__setattr__(self, "status", status)
        if status is DiagnosticExecutionStatus.COMPLETED:
            if self.error is not None:
                raise ValueError(
                    "error must be None when status is COMPLETED"
                )
        elif not isinstance(self.error, str) or not self.error.strip():
            raise ValueError(
                f"error must be a non-empty string when status is "
                f"{status.value} (failures carry their reason)"
            )
        for field_name in ("provenance_method", "provenance_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string "
                    "(results carry their provenance)"
                )

    @staticmethod
    def _checked_ref_tuple(value: object, field_name: str) -> Tuple[str, ...]:
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

    @property
    def outcome(self) -> str:
        """E0-compatible outcome string for ``record_test_result``."""
        return self.status.value

    def measured_by_name(self, name: str) -> MetricResult:
        """Fetch one measured outcome by metric name."""
        for item in self.measured:
            if item.name == name:
                return item
        raise KeyError(f"no measured outcome {name!r}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "result_id": self.result_id,
            "test_id": self.test_id,
            "execution_fingerprint": self.execution_fingerprint,
            "baseline_evaluation_id": self.baseline_evaluation_id,
            "baseline_fingerprint": self.baseline_fingerprint,
            "intervention_fingerprint": self.intervention_fingerprint,
            "record_fps": list(self.record_fps),
            "evidence_refs": list(self.evidence_refs),
            "measured": [item.to_dict() for item in self.measured],
            "prediction_ids": list(self.prediction_ids),
            "status": self.status.value,
            "outcome": self.outcome,
            "error": self.error,
            "provenance_method": self.provenance_method,
            "provenance_version": self.provenance_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DiagnosticTestResult":
        if not isinstance(payload, Mapping):
            raise TypeError("DiagnosticTestResult payload must be a mapping")
        known = {
            "result_id", "test_id", "execution_fingerprint",
            "baseline_evaluation_id", "baseline_fingerprint",
            "intervention_fingerprint", "record_fps", "evidence_refs",
            "measured", "prediction_ids", "status", "outcome", "error",
            "provenance_method", "provenance_version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown DiagnosticTestResult fields: {sorted(extra)}"
            )
        try:
            status = payload.get("status", payload.get("outcome", "COMPLETED"))
            return cls(
                result_id=payload["result_id"],
                test_id=payload["test_id"],
                execution_fingerprint=payload["execution_fingerprint"],
                baseline_evaluation_id=payload["baseline_evaluation_id"],
                baseline_fingerprint=payload["baseline_fingerprint"],
                intervention_fingerprint=payload["intervention_fingerprint"],
                record_fps=tuple(payload.get("record_fps", ())),
                evidence_refs=tuple(payload.get("evidence_refs", ())),
                measured=tuple(
                    MetricResult.from_dict(item)
                    for item in payload.get("measured", ())
                ),
                prediction_ids=tuple(payload.get("prediction_ids", ())),
                status=status,
                error=payload.get("error"),
                provenance_method=payload["provenance_method"],
                provenance_version=payload["provenance_version"],
            )
        except KeyError as exc:
            raise ValueError(
                f"DiagnosticTestResult payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        """Deterministic identity over every result field."""
        return fingerprint_of_dict(self.to_dict())
