"""LearnedContext: validated failure knowledge as a first-class object (E4).

A ``LearnedContext`` is structured, versioned, reproducible,
provenance-preserving, fingerprinted knowledge extracted from a
validated repair. It is immutable; lifecycle moves through explicit
status transitions only::

    CANDIDATE       (extracted, not yet judged)
    VALIDATED       (admission checks passed, not yet stored)
    ADMITTED        (stored in persistent memory)
    QUARANTINED     (suspicious: needs review, never served)
    REJECTED        (terminally refused admission)
    SUPERSEDED      (replaced by a newer context version)

A merely diagnosed candidate must never masquerade as validated
knowledge: only the admission gate may move status beyond CANDIDATE,
and only validated repairs may enter persistent memory.

Conventions follow E0 exactly: frozen dataclass, strict validation,
``to_dict``/``from_dict`` with unknown-field rejection, SHA-256
fingerprint over canonical JSON. No wall-clock time, no UUIDs, no
randomness enters identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Tuple

from evaluation.contracts.fingerprints import fingerprint_of_dict, freeze, thaw


class ContextStatus(str, Enum):
    """Closed lifecycle vocabulary for learned context."""

    CANDIDATE = "CANDIDATE"
    VALIDATED = "VALIDATED"
    ADMITTED = "ADMITTED"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"

    def to_str(self) -> str:
        return self.value

    @classmethod
    def from_str(cls, value: object) -> "ContextStatus":
        for member in cls:
            if value == member.value:
                return member
        known = sorted(member.value for member in cls)
        raise ValueError(f"unknown ContextStatus {value!r}; known: {known}")


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_str_tuple(value: object, field_name: str) -> Tuple[str, ...]:
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


@dataclass(frozen=True)
class LearnedContext:
    """One structured unit of validated failure knowledge."""

    context_id: str
    agent_id: str
    source_evaluation_id: str
    failure_mechanism: str
    observed_pattern: str
    triggering_conditions: Tuple[str, ...] = field(default_factory=tuple)
    diagnostic_evidence: Tuple[str, ...] = field(default_factory=tuple)
    corrective_principle: str = ""
    applicability_conditions: Tuple[str, ...] = field(default_factory=tuple)
    contraindications: Tuple[str, ...] = field(default_factory=tuple)
    expected_effect: str = ""
    validation_result: str = ""
    validation_metrics: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    held_out_evidence: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    provenance: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    status: ContextStatus = ContextStatus.CANDIDATE
    version: str = "v1"

    def __post_init__(self) -> None:
        for field_name in (
            "context_id",
            "agent_id",
            "source_evaluation_id",
            "failure_mechanism",
            "observed_pattern",
            "corrective_principle",
            "expected_effect",
            "validation_result",
            "version",
        ):
            _require_str(getattr(self, field_name), field_name)
        for field_name in (
            "triggering_conditions",
            "applicability_conditions",
            "contraindications",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_str_tuple(getattr(self, field_name), field_name),
            )
        evidence = _require_str_tuple(
            self.diagnostic_evidence, "diagnostic_evidence"
        )
        if not evidence:
            raise ValueError(
                "diagnostic_evidence must be non-empty: knowledge "
                "without evidence cannot be admitted"
            )
        object.__setattr__(self, "diagnostic_evidence", evidence)
        for field_name in (
            "validation_metrics",
            "held_out_evidence",
            "provenance",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, Mapping):
                raise TypeError(f"{field_name} must be a mapping")
            object.__setattr__(self, field_name, freeze(dict(value)))
        if not dict(self.provenance):
            raise ValueError(
                "provenance must be a non-empty mapping: every memory "
                "must answer why the agent knows this"
            )
        status = self.status
        if isinstance(status, str) and not isinstance(status, ContextStatus):
            status = ContextStatus.from_str(status)
        if not isinstance(status, ContextStatus):
            raise TypeError(
                f"status must be a ContextStatus, got {self.status!r}"
            )
        object.__setattr__(self, "status", status)

    def with_status(self, status: ContextStatus | str) -> "LearnedContext":
        """Pure status transition returning a new instance."""
        if isinstance(status, str) and not isinstance(status, ContextStatus):
            status = ContextStatus.from_str(status)
        if not isinstance(status, ContextStatus):
            raise TypeError(
                f"status must be a ContextStatus, got {status!r}"
            )
        current = self.status
        allowed = {
            ContextStatus.CANDIDATE: (
                ContextStatus.VALIDATED,
                ContextStatus.QUARANTINED,
                ContextStatus.REJECTED,
            ),
            ContextStatus.VALIDATED: (
                ContextStatus.ADMITTED,
                ContextStatus.QUARANTINED,
                ContextStatus.REJECTED,
            ),
            ContextStatus.ADMITTED: (ContextStatus.SUPERSEDED,),
            ContextStatus.QUARANTINED: (
                ContextStatus.VALIDATED,
                ContextStatus.REJECTED,
            ),
            ContextStatus.REJECTED: (),
            ContextStatus.SUPERSEDED: (),
        }
        if status not in allowed[current] and status is not current:
            raise ValueError(
                f"illegal status transition {current.value} -> "
                f"{status.value}"
            )
        return LearnedContext(
            context_id=self.context_id,
            agent_id=self.agent_id,
            source_evaluation_id=self.source_evaluation_id,
            failure_mechanism=self.failure_mechanism,
            observed_pattern=self.observed_pattern,
            triggering_conditions=self.triggering_conditions,
            diagnostic_evidence=self.diagnostic_evidence,
            corrective_principle=self.corrective_principle,
            applicability_conditions=self.applicability_conditions,
            contraindications=self.contraindications,
            expected_effect=self.expected_effect,
            validation_result=self.validation_result,
            validation_metrics=dict(self.validation_metrics),
            held_out_evidence=dict(self.held_out_evidence),
            provenance=dict(self.provenance),
            status=status,
            version=self.version,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "context_id": self.context_id,
            "agent_id": self.agent_id,
            "source_evaluation_id": self.source_evaluation_id,
            "failure_mechanism": self.failure_mechanism,
            "observed_pattern": self.observed_pattern,
            "triggering_conditions": list(self.triggering_conditions),
            "diagnostic_evidence": list(self.diagnostic_evidence),
            "corrective_principle": self.corrective_principle,
            "applicability_conditions": list(
                self.applicability_conditions
            ),
            "contraindications": list(self.contraindications),
            "expected_effect": self.expected_effect,
            "validation_result": self.validation_result,
            "validation_metrics": thaw(self.validation_metrics),
            "held_out_evidence": thaw(self.held_out_evidence),
            "provenance": thaw(self.provenance),
            "status": self.status.value,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LearnedContext":
        if not isinstance(payload, Mapping):
            raise TypeError("LearnedContext payload must be a mapping")
        known = {
            "context_id", "agent_id", "source_evaluation_id",
            "failure_mechanism", "observed_pattern",
            "triggering_conditions", "diagnostic_evidence",
            "corrective_principle", "applicability_conditions",
            "contraindications", "expected_effect",
            "validation_result", "validation_metrics",
            "held_out_evidence", "provenance", "status", "version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown LearnedContext fields: {sorted(extra)}"
            )
        try:
            return cls(
                context_id=payload["context_id"],
                agent_id=payload["agent_id"],
                source_evaluation_id=payload["source_evaluation_id"],
                failure_mechanism=payload["failure_mechanism"],
                observed_pattern=payload["observed_pattern"],
                triggering_conditions=tuple(
                    payload.get("triggering_conditions", ())
                ),
                diagnostic_evidence=tuple(payload["diagnostic_evidence"]),
                corrective_principle=payload["corrective_principle"],
                applicability_conditions=tuple(
                    payload.get("applicability_conditions", ())
                ),
                contraindications=tuple(
                    payload.get("contraindications", ())
                ),
                expected_effect=payload["expected_effect"],
                validation_result=payload["validation_result"],
                validation_metrics=dict(
                    payload.get("validation_metrics", {})
                ),
                held_out_evidence=dict(
                    payload.get("held_out_evidence", {})
                ),
                provenance=dict(payload["provenance"]),
                status=payload.get("status", "CANDIDATE"),
                version=payload.get("version", "v1"),
            )
        except KeyError as exc:
            raise ValueError(
                f"LearnedContext payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())
