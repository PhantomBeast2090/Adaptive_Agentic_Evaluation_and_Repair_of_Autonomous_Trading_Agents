"""Append-only versioned memory store (E4-C).

``MemoryStore`` is an immutable, fingerprinted sequence of admitted
``StoredEntry`` records: C0 (empty) → C1 → C2 → … Every ``admit``
returns a new store; nothing already stored can change. Admission is
possible only through ``admit`` with a matching ADMITTED verdict, so
no caller can bypass the gate and insert arbitrary knowledge.

Context identity across versions is exact: the store fingerprint
reconstructs precisely which knowledge was available, so Agent + C0
versus Agent + C1 is always decidable and reproducible.

Conventions follow E0 exactly: frozen dataclasses, strict
validation, ``to_dict``/``from_dict`` with unknown-field rejection,
SHA-256 fingerprints. No wall-clock time, no UUIDs, no randomness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

from evaluation.context.learned import ContextStatus, LearnedContext
from evaluation.contracts.fingerprints import fingerprint_of_dict

STORE_METHOD = "append-only-memory"
STORE_VERSION = "v1"


@dataclass(frozen=True)
class StoredEntry:
    """One admitted knowledge object with its admission provenance."""

    entry_id: str
    context: LearnedContext
    verdict_fingerprint: str
    sequence: int
    candidate_fingerprint: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.entry_id, str) or not self.entry_id.strip():
            raise ValueError("entry_id must be a non-empty string")
        if not isinstance(self.context, LearnedContext):
            raise TypeError(
                "context must be a LearnedContext, "
                f"got {type(self.context).__name__}"
            )
        if self.context.status is not ContextStatus.ADMITTED:
            raise ValueError(
                "stored entries must carry ADMITTED status; "
                f"got {self.context.status.value}"
            )
        if (
            not isinstance(self.verdict_fingerprint, str)
            or not self.verdict_fingerprint.strip()
        ):
            raise ValueError(
                "verdict_fingerprint must be a non-empty string"
            )
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 1
        ):
            raise ValueError("sequence must be a positive int")
        if (
            not isinstance(self.candidate_fingerprint, str)
            or not self.candidate_fingerprint.strip()
        ):
            raise ValueError(
                "candidate_fingerprint must be a non-empty string: "
                "duplicate detection compares validated candidates, "
                "whose fingerprints legitimately differ from the "
                "stored ADMITTED objects"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "context": self.context.to_dict(),
            "verdict_fingerprint": self.verdict_fingerprint,
            "sequence": self.sequence,
            "candidate_fingerprint": self.candidate_fingerprint,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StoredEntry":
        if not isinstance(payload, Mapping):
            raise TypeError("StoredEntry payload must be a mapping")
        known = {
            "entry_id", "context", "verdict_fingerprint", "sequence",
            "candidate_fingerprint",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown StoredEntry fields: {sorted(extra)}"
            )
        try:
            return cls(
                entry_id=payload["entry_id"],
                context=LearnedContext.from_dict(payload["context"]),
                verdict_fingerprint=payload["verdict_fingerprint"],
                sequence=payload["sequence"],
                candidate_fingerprint=payload["candidate_fingerprint"],
            )
        except KeyError as exc:
            raise ValueError(
                f"StoredEntry payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


@dataclass(frozen=True)
class MemoryStore:
    """Immutable append-only sequence of admitted entries."""

    store_id: str
    entries: Tuple[StoredEntry, ...] = ()
    method: str = STORE_METHOD
    method_version: str = STORE_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.store_id, str) or not self.store_id.strip():
            raise ValueError("store_id must be a non-empty string")
        entries = self.entries
        if isinstance(entries, str) or not isinstance(entries, (tuple, list)):
            raise TypeError("entries must be a tuple/list")
        entries = tuple(entries)
        for entry in entries:
            if not isinstance(entry, StoredEntry):
                raise TypeError(
                    "entries must contain StoredEntry, "
                    f"got {type(entry).__name__}"
                )
        sequences = [entry.sequence for entry in entries]
        if sequences != sorted(sequences) or len(set(sequences)) != len(
            sequences
        ):
            raise ValueError(
                "entry sequences must be unique and ordered"
            )
        object.__setattr__(self, "entries", entries)
        for field_name in ("method", "method_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )

    @property
    def store_version(self) -> int:
        """Number of admitted entries: C0 is empty, C1 has one, …"""
        return len(self.entries)

    def contains(self, context_fingerprint: str) -> bool:
        """True when identical validated knowledge is already stored.

        Compares validated-candidate fingerprints (status VALIDATED),
        not stored ADMITTED fingerprints: the status transition
        legitimately changes identity, so duplication is judged at
        the gate's level, not the store's.
        """
        if not isinstance(context_fingerprint, str):
            raise TypeError("context_fingerprint must be a string")
        return any(
            entry.candidate_fingerprint == context_fingerprint
            for entry in self.entries
        )

    def find_conflicts(self, candidate: LearnedContext) -> Tuple[str, ...]:
        """Entry ids contradicting a candidate (deterministic rule).

        A conflict is the same agent, same failure mechanism, and
        same applicability with a different corrective principle:
        two such entries cannot both guide future reasoning, so the
        newcomer quarantines instead of storing.
        """
        if not isinstance(candidate, LearnedContext):
            raise TypeError(
                "candidate must be a LearnedContext, "
                f"got {type(candidate).__name__}"
            )
        return tuple(
            entry.entry_id
            for entry in self.entries
            if entry.context.agent_id == candidate.agent_id
            and entry.context.failure_mechanism
            == candidate.failure_mechanism
            and entry.context.applicability_conditions
            == candidate.applicability_conditions
            and entry.context.corrective_principle
            != candidate.corrective_principle
        )

    def admit(self, validated: LearnedContext, verdict: Any) -> "MemoryStore":
        """Append one gate-admitted candidate; return the new store.

        Refuses anything but a VALIDATED candidate with a matching
        ADMITTED verdict, so the gate cannot be bypassed. The input
        store is never mutated.
        """
        from evaluation.context.gate import AdmissionDecision

        if not isinstance(validated, LearnedContext):
            raise TypeError(
                "validated must be a LearnedContext, "
                f"got {type(validated).__name__}"
            )
        if validated.status is not ContextStatus.VALIDATED:
            raise ValueError(
                "only VALIDATED candidates may be admitted; "
                f"got {validated.status.value}"
            )
        decision = getattr(verdict, "decision", None)
        if decision is not AdmissionDecision.ADMITTED:
            raise ValueError(
                "admission requires an ADMITTED verdict; "
                f"got {decision!r}"
            )
        if getattr(verdict, "candidate_fingerprint", None) != (
            validated.fingerprint()
        ):
            raise ValueError(
                "verdict does not describe this candidate: refusing"
            )
        if self.contains(validated.fingerprint()):
            raise ValueError(
                "identical knowledge already stored: refusing duplicate"
            )
        admitted = validated.with_status(ContextStatus.ADMITTED)
        entry = StoredEntry(
            entry_id=f"mem-{admitted.fingerprint()[:16]}",
            context=admitted,
            verdict_fingerprint=verdict.fingerprint(),
            sequence=len(self.entries) + 1,
            candidate_fingerprint=validated.fingerprint(),
        )
        return MemoryStore(
            store_id=self.store_id,
            entries=self.entries + (entry,),
            method=self.method,
            method_version=self.method_version,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "store_id": self.store_id,
            "entries": [entry.to_dict() for entry in self.entries],
            "method": self.method,
            "version": self.method_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MemoryStore":
        if not isinstance(payload, Mapping):
            raise TypeError("MemoryStore payload must be a mapping")
        known = {"store_id", "entries", "method", "version"}
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown MemoryStore fields: {sorted(extra)}"
            )
        try:
            return cls(
                store_id=payload["store_id"],
                entries=tuple(
                    StoredEntry.from_dict(item)
                    for item in payload.get("entries", ())
                ),
                method=payload.get("method", STORE_METHOD),
                method_version=payload.get("version", STORE_VERSION),
            )
        except KeyError as exc:
            raise ValueError(
                f"MemoryStore payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())
