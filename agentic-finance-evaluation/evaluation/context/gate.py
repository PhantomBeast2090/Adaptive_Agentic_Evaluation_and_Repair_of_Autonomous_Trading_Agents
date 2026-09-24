"""Validation-gated memory admission (E4-C).

``adjudicate`` judges a CANDIDATE ``LearnedContext`` against live
artefacts and store state, returning a validated candidate plus an
explicit verdict. Only ADMITTED verdicts may enter the store, and
only through ``MemoryStore.admit`` — there is no path that inserts
an arbitrary context directly. Failed, unresolved, or rejected
repairs can never enter persistent memory; neither can candidates
with missing provenance, mismatched fingerprints, duplicates, or
contradictory predecessors (those quarantine instead).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Mapping, Tuple

from evaluation.context.learned import ContextStatus, LearnedContext
from evaluation.context.memory import MemoryStore
from evaluation.contracts.fingerprints import fingerprint_of_dict
from evaluation.diagnostics.repair.regression import RegressionAnalysis
from evaluation.diagnostics.repair.results import RepairResult
from evaluation.diagnostics.repair.validation import ValidationReport


class AdmissionDecision(str, Enum):
    """Closed verdict vocabulary for memory admission."""

    ADMITTED = "ADMITTED"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"

    def to_str(self) -> str:
        return self.value

    @classmethod
    def from_str(cls, value: object) -> "AdmissionDecision":
        for member in cls:
            if value == member.value:
                return member
        known = sorted(member.value for member in cls)
        raise ValueError(f"unknown AdmissionDecision {value!r}; known: {known}")


@dataclass(frozen=True)
class AdmissionVerdict:
    """One explicit admission judgement for one candidate."""

    candidate_id: str
    candidate_fingerprint: str
    decision: AdmissionDecision = AdmissionDecision.REJECTED
    reason: str = ""
    method: str = ""
    method_version: str = ""

    def __post_init__(self) -> None:
        for field_name in ("candidate_id", "candidate_fingerprint"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        decision = self.decision
        if isinstance(decision, str) and not isinstance(
            decision, AdmissionDecision
        ):
            decision = AdmissionDecision.from_str(decision)
        if not isinstance(decision, AdmissionDecision):
            raise TypeError(
                "decision must be an AdmissionDecision member, "
                f"got {self.decision!r}"
            )
        object.__setattr__(self, "decision", decision)
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must be a non-empty string")
        for field_name in ("method", "method_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_fingerprint": self.candidate_fingerprint,
            "decision": self.decision.value,
            "reason": self.reason,
            "method": self.method,
            "version": self.method_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AdmissionVerdict":
        if not isinstance(payload, Mapping):
            raise TypeError("AdmissionVerdict payload must be a mapping")
        known = {
            "candidate_id", "candidate_fingerprint", "decision",
            "reason", "method", "version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown AdmissionVerdict fields: {sorted(extra)}"
            )
        try:
            return cls(
                candidate_id=payload["candidate_id"],
                candidate_fingerprint=payload["candidate_fingerprint"],
                decision=payload.get("decision", "REJECTED"),
                reason=payload["reason"],
                method=payload["method"],
                method_version=payload.get("version", ""),
            )
        except KeyError as exc:
            raise ValueError(
                f"AdmissionVerdict payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


GATE_METHOD = "validation-gate"
GATE_VERSION = "v1"


def _reject(
    candidate: LearnedContext, reason: str
) -> Tuple[LearnedContext, AdmissionVerdict]:
    return candidate, AdmissionVerdict(
        candidate_id=candidate.context_id,
        candidate_fingerprint=candidate.fingerprint(),
        decision=AdmissionDecision.REJECTED,
        reason=reason,
        method=GATE_METHOD,
        method_version=GATE_VERSION,
    )


def _decide(
    validated: LearnedContext,
    decision: AdmissionDecision,
    reason: str,
) -> Tuple[LearnedContext, AdmissionVerdict]:
    return validated, AdmissionVerdict(
        candidate_id=validated.context_id,
        candidate_fingerprint=validated.fingerprint(),
        decision=decision,
        reason=reason,
        method=GATE_METHOD,
        method_version=GATE_VERSION,
    )


def adjudicate(
    *,
    candidate: LearnedContext,
    result: RepairResult,
    report: ValidationReport,
    analysis: RegressionAnalysis,
    store: MemoryStore,
    proposal: Any = None,
) -> Tuple[LearnedContext, AdmissionVerdict]:
    """Judge one candidate; return (possibly transitioned, verdict).

    The gate judges CANDIDATE objects only, cross-checks provenance
    fingerprints against the live artefacts, requires an ACCEPTED
    repair decision, and consults store state for duplicates and
    contradictions. It never mutates inputs and never writes memory.

    When ``proposal`` is supplied, the result↔proposal linkage is
    additionally verified (``result.proposal_fingerprint`` must equal
    the live proposal fingerprint, and the candidate's recorded
    proposal fingerprint must match too), closing cross-repair
    artefact mixing. Callers with the proposal available should
    always supply it.
    """
    for name, value, kind in (
        ("candidate", candidate, LearnedContext),
        ("result", result, RepairResult),
        ("report", report, ValidationReport),
        ("analysis", analysis, RegressionAnalysis),
        ("store", store, MemoryStore),
    ):
        if not isinstance(value, kind):
            raise TypeError(
                f"{name} must be a {kind.__name__}, "
                f"got {type(value).__name__}"
            )
    if candidate.status is not ContextStatus.CANDIDATE:
        raise ValueError(
            "gate judges CANDIDATE objects only; "
            f"got {candidate.status.value}"
        )
    decision = (
        result.decision.value
        if hasattr(result.decision, "value")
        else str(result.decision)
    )
    if decision != "ACCEPTED":
        return _reject(
            candidate,
            f"repair decision {decision!r} is not ACCEPTED: failed, "
            "unresolved, and rejected repairs can never enter "
            "persistent memory",
        )
    provenance = dict(candidate.provenance)
    expected = {
        "proposal_fingerprint": None,
        "repair_fingerprint": result.fingerprint(),
        "validation_fingerprint": report.fingerprint(),
        "analysis_fingerprint": analysis.fingerprint(),
    }
    for key, actual in expected.items():
        if key == "proposal_fingerprint":
            continue
        stored = provenance.get(key)
        if not isinstance(stored, str) or not stored:
            return _reject(
                candidate,
                f"provenance missing {key!r}: knowledge without "
                "complete lineage cannot be admitted",
            )
        if stored != actual:
            return _reject(
                candidate,
                f"provenance {key!r} does not match the live artefact: "
                "refusing mismatched knowledge",
            )
    if not isinstance(provenance.get("proposal_fingerprint"), str) or (
        not provenance["proposal_fingerprint"]
    ):
        return _reject(
            candidate,
            "provenance missing proposal_fingerprint",
        )
    if proposal is not None:
        from evaluation.diagnostics.repair.proposal import RepairProposal

        if not isinstance(proposal, RepairProposal):
            raise TypeError(
                "proposal must be a RepairProposal, "
                f"got {type(proposal).__name__}"
            )
        if result.proposal_fingerprint != proposal.fingerprint():
            return _reject(
                candidate,
                "result does not reference the supplied proposal: "
                "cross-repair artefact mixing refused",
            )
        if provenance["proposal_fingerprint"] != proposal.fingerprint():
            return _reject(
                candidate,
                "candidate provenance does not reference the supplied "
                "proposal: refusing mismatched knowledge",
            )
    validated = candidate.with_status(ContextStatus.VALIDATED)
    if store.contains(validated.fingerprint()):
        return _decide(
            validated,
            AdmissionDecision.DUPLICATE,
            "identical knowledge already stored: store unchanged",
        )
    conflicts = store.find_conflicts(validated)
    if conflicts:
        quarantined = candidate.with_status(ContextStatus.QUARANTINED)
        return quarantined, AdmissionVerdict(
            candidate_id=candidate.context_id,
            candidate_fingerprint=candidate.fingerprint(),
            decision=AdmissionDecision.QUARANTINED,
            reason=(
                "contradicts stored entry "
                f"{conflicts[0]!r} on the same mechanism: held for "
                "review, never served"
            ),
            method=GATE_METHOD,
            method_version=GATE_VERSION,
        )
    validated = candidate.with_status(ContextStatus.VALIDATED)
    return _decide(
        validated,
        AdmissionDecision.ADMITTED,
        "ACCEPTED repair with complete matching provenance "
        "and no duplicate or contradiction",
    )
