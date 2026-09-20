"""E2-F repair/validation budget ledger (accounting owner).

``RepairBudgetLedger`` is the single accounting owner for E2-F budget
consumption. It derives usage from explicit, persisted entry tuples — never
from hidden counters, module state, or process-local values:

* one ``RepairAdmission`` entry = exactly 1 repair unit;
* one ``ValidationConsumption`` entry = exactly N validation-run units,
  with N in {1, 2, 3} (3 on completion, invoked-run count on partial failure).

Entries mirror the frozen E0 note slots (``note_repair_candidate`` /
``note_validation_result``) as the colocated audit trail, and
``from_evaluation_state`` rebuilds the authoritative ledger from those
persisted slots — so accounting is reconstructible from persisted state, not
from ephemeral result objects. Admission markers carry the
``repair-admission-v1`` discriminator and the ``@admission`` identifier
namespace, which is disjoint from applied-candidate identifiers
(``@candidate-``): admission metadata can never be mistaken for evidence
that a repair candidate was successfully applied.

All records are frozen dataclasses with strict ``to_dict`` / ``from_dict``
(unknown-field rejection, codebase idiom) and SHA-256 fingerprints over
canonical JSON. No wall-clock, UUID, process identity, or nondeterminism
enters any record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Tuple

from evaluation.contracts.fingerprints import fingerprint_of_dict

LEDGER_METHOD = "e2f-budget-ledger"
LEDGER_VERSION = "v1"

ADMISSION_RECORD_KIND = "repair-admission-v1"

COMPLETED_OUTCOME = "completed"
PARTIAL_OUTCOME = "partial"

_VALIDATION_OUTCOMES = (COMPLETED_OUTCOME, PARTIAL_OUTCOME)


def _require_non_empty_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class RepairAdmission:
    """One admitted repair attempt: exactly 1 repair unit, recorded pre-work."""

    repair_id: str
    diagnostic_id: str
    hypothesis_id: str
    record_kind: str = ADMISSION_RECORD_KIND

    def __post_init__(self) -> None:
        _require_non_empty_str(self.repair_id, "repair_id")
        _require_non_empty_str(self.diagnostic_id, "diagnostic_id")
        _require_non_empty_str(self.hypothesis_id, "hypothesis_id")
        if self.record_kind != ADMISSION_RECORD_KIND:
            raise ValueError(
                "record_kind must be "
                f"{ADMISSION_RECORD_KIND!r}, got {self.record_kind!r}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repair_id": self.repair_id,
            "diagnostic_id": self.diagnostic_id,
            "hypothesis_id": self.hypothesis_id,
            "record_kind": self.record_kind,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RepairAdmission":
        if not isinstance(payload, Mapping):
            raise TypeError("RepairAdmission payload must be a mapping")
        known = {"repair_id", "diagnostic_id", "hypothesis_id", "record_kind"}
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown RepairAdmission fields: {sorted(extra)}"
            )
        try:
            return cls(
                repair_id=payload["repair_id"],
                diagnostic_id=payload["diagnostic_id"],
                hypothesis_id=payload["hypothesis_id"],
                record_kind=payload.get("record_kind", ADMISSION_RECORD_KIND),
            )
        except KeyError as exc:
            raise ValueError(
                f"RepairAdmission payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


@dataclass(frozen=True)
class ValidationConsumption:
    """Validation-run units consumed by one admitted validation cycle."""

    repair_id: str
    runs_consumed: int
    outcome: str = COMPLETED_OUTCOME

    def __post_init__(self) -> None:
        _require_non_empty_str(self.repair_id, "repair_id")
        if (
            isinstance(self.runs_consumed, bool)
            or not isinstance(self.runs_consumed, int)
            or self.runs_consumed not in (1, 2, 3)
        ):
            raise ValueError(
                "runs_consumed must be 1, 2, or 3 "
                f"(invoked-run count), got {self.runs_consumed!r}"
            )
        if self.outcome not in _VALIDATION_OUTCOMES:
            raise ValueError(
                f"outcome must be one of {sorted(_VALIDATION_OUTCOMES)}, "
                f"got {self.outcome!r}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repair_id": self.repair_id,
            "runs_consumed": self.runs_consumed,
            "outcome": self.outcome,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidationConsumption":
        if not isinstance(payload, Mapping):
            raise TypeError("ValidationConsumption payload must be a mapping")
        known = {"repair_id", "runs_consumed", "outcome"}
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown ValidationConsumption fields: {sorted(extra)}"
            )
        try:
            return cls(
                repair_id=payload["repair_id"],
                runs_consumed=payload["runs_consumed"],
                outcome=payload.get("outcome", COMPLETED_OUTCOME),
            )
        except KeyError as exc:
            raise ValueError(
                f"ValidationConsumption payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


def admission_marker_id(repair_id: str) -> str:
    """Deterministic audit identifier for an admission marker.

    The ``@admission`` namespace is disjoint from applied-candidate
    identifiers (``{agent_id}@candidate-{...}``), so markers satisfy the
    frozen E0 ``candidate_id`` requirement without colliding with real
    candidate provenance.
    """
    _require_non_empty_str(repair_id, "repair_id")
    return f"{repair_id}@admission"


@dataclass(frozen=True)
class RepairBudgetLedger:
    """Authoritative, replayable owner of E2-F budget usage.

    Usage is derived from explicit entry tuples: ``repairs_used`` counts
    admissions, ``validation_runs_used`` sums consumptions. Functional
    append (``admit`` / ``record_validation`` return new instances) keeps
    the ledger itself immutable and fingerprintable.
    """

    ledger_id: str
    admissions: Tuple[RepairAdmission, ...] = field(default_factory=tuple)
    consumptions: Tuple[ValidationConsumption, ...] = field(
        default_factory=tuple
    )
    method: str = LEDGER_METHOD
    method_version: str = LEDGER_VERSION

    def __post_init__(self) -> None:
        _require_non_empty_str(self.ledger_id, "ledger_id")
        admissions = self.admissions
        if isinstance(admissions, str) or not isinstance(
            admissions, (tuple, list)
        ):
            raise TypeError("admissions must be a tuple/list")
        admissions = tuple(admissions)
        for entry in admissions:
            if not isinstance(entry, RepairAdmission):
                raise TypeError(
                    "admissions must contain RepairAdmission, "
                    f"got {type(entry).__name__}"
                )
        object.__setattr__(self, "admissions", admissions)
        consumptions = self.consumptions
        if isinstance(consumptions, str) or not isinstance(
            consumptions, (tuple, list)
        ):
            raise TypeError("consumptions must be a tuple/list")
        consumptions = tuple(consumptions)
        for entry in consumptions:
            if not isinstance(entry, ValidationConsumption):
                raise TypeError(
                    "consumptions must contain ValidationConsumption, "
                    f"got {type(entry).__name__}"
                )
        object.__setattr__(self, "consumptions", consumptions)
        _require_non_empty_str(self.method, "method")
        _require_non_empty_str(self.method_version, "method_version")

    @property
    def repairs_used(self) -> int:
        """Repair units consumed: exactly one per admitted attempt."""
        return len(self.admissions)

    @property
    def validation_runs_used(self) -> int:
        """Validation-run units consumed across admitted cycles."""
        return sum(entry.runs_consumed for entry in self.consumptions)

    def admit(
        self, *, repair_id: str, diagnostic_id: str, hypothesis_id: str
    ) -> "RepairBudgetLedger":
        """Return a new ledger with one repair unit consumed (pre-work)."""
        return RepairBudgetLedger(
            ledger_id=self.ledger_id,
            admissions=self.admissions
            + (
                RepairAdmission(
                    repair_id=repair_id,
                    diagnostic_id=diagnostic_id,
                    hypothesis_id=hypothesis_id,
                ),
            ),
            consumptions=self.consumptions,
            method=self.method,
            method_version=self.method_version,
        )

    def record_validation(
        self, *, repair_id: str, runs_consumed: int, outcome: str
    ) -> "RepairBudgetLedger":
        """Return a new ledger with validation-run consumption recorded."""
        return RepairBudgetLedger(
            ledger_id=self.ledger_id,
            admissions=self.admissions,
            consumptions=self.consumptions
            + (
                ValidationConsumption(
                    repair_id=repair_id,
                    runs_consumed=runs_consumed,
                    outcome=outcome,
                ),
            ),
            method=self.method,
            method_version=self.method_version,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ledger_id": self.ledger_id,
            "method": self.method,
            "version": self.method_version,
            "admissions": [entry.to_dict() for entry in self.admissions],
            "consumptions": [entry.to_dict() for entry in self.consumptions],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RepairBudgetLedger":
        if not isinstance(payload, Mapping):
            raise TypeError("RepairBudgetLedger payload must be a mapping")
        known = {
            "ledger_id",
            "method",
            "version",
            "admissions",
            "consumptions",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown RepairBudgetLedger fields: {sorted(extra)}"
            )
        try:
            return cls(
                ledger_id=payload["ledger_id"],
                admissions=tuple(
                    RepairAdmission.from_dict(item)
                    for item in payload.get("admissions", ())
                ),
                consumptions=tuple(
                    ValidationConsumption.from_dict(item)
                    for item in payload.get("consumptions", ())
                ),
                method=payload.get("method", LEDGER_METHOD),
                method_version=payload.get("version", LEDGER_VERSION),
            )
        except KeyError as exc:
            raise ValueError(
                f"RepairBudgetLedger payload missing {exc}"
            ) from exc

    @classmethod
    def from_evaluation_state(cls, evaluation_state: Any) -> "RepairBudgetLedger":
        """Rebuild the authoritative ledger from persisted E0 note slots.

        Admission entries are the ``repair_candidates`` notes carrying the
        admission discriminator; consumption entries are the
        ``validation_results`` notes carrying ``validation_runs_consumed``.
        Provenance notes without these keys are audit trail, not accounting,
        and contribute nothing — so markers can never inflate usage beyond
        admitted attempts, and real provenance can never be double-counted.
        """
        ledger_id = (
            f"ledger-{evaluation_state.evaluation_id}"
        )
        admissions = []
        for note in evaluation_state.repair_candidates:
            if (
                isinstance(note, Mapping)
                and note.get("record_kind") == ADMISSION_RECORD_KIND
            ):
                admissions.append(
                    RepairAdmission(
                        repair_id=note["repair_id"],
                        diagnostic_id=note["diagnostic_id"],
                        hypothesis_id=note["hypothesis_id"],
                    )
                )
        consumptions = []
        for note in evaluation_state.validation_results:
            consumed = note.get("validation_runs_consumed") if isinstance(
                note, Mapping
            ) else None
            if (
                isinstance(consumed, int)
                and not isinstance(consumed, bool)
            ):
                consumptions.append(
                    ValidationConsumption(
                        repair_id=note.get("repair_id") or "unknown",
                        runs_consumed=consumed,
                        outcome=note.get("outcome", COMPLETED_OUTCOME),
                    )
                )
        return cls(
            ledger_id=ledger_id,
            admissions=tuple(admissions),
            consumptions=tuple(consumptions),
        )

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())
