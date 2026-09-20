"""Arm lineage and the sealed held-out baseline (orchestration only).

The transition table makes illegal arm sequences unrepresentable at the
call site: anything outside the allowed edges raises before execution.
``SealedBaseline`` locks N-H scientific contents from Phase A until
final assembly — diagnosis, repair, validation, and stopping never
receive it (their signatures have no such parameter), and its payload
cannot be read, released twice, released out of phase, or released
after tampering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.baseline.results import BaselineResult
from evaluation.contracts.fingerprints import fingerprint_of_dict, freeze, thaw
from experiments.harness.errors import (
    LineageError,
    SealIntegrityError,
    SealedAccessError,
    TransitionError,
)

ASSEMBLY_PHASE = "assembly"

ALLOWED_TRANSITIONS: Tuple[Tuple[str, str], ...] = (
    ("N-D", "D-F"),
    ("N-D", "D-A"),
    ("N-H", "SEALED"),
    ("D-F", "REPAIR"),
    ("D-A", "REPAIR"),
    ("REPAIR", "R-D"),
    ("R-D", "R-H"),
    ("R-H", "ASSEMBLY"),
)

_REPAIR_LINEAGE_DECISIONS = ("ACCEPTED", "REJECTED", "UNRESOLVED")


def assert_transition(frm: str, to: str) -> None:
    """Raise unless the arm transition is explicitly allowed."""
    if (frm, to) not in ALLOWED_TRANSITIONS:
        allowed = sorted(f"{a} -> {b}" for a, b in ALLOWED_TRANSITIONS)
        raise TransitionError(
            f"forbidden arm transition {frm!r} -> {to!r}; allowed: {allowed}"
        )


def require_repair_lineage(
    repair_decision: str, validation_fingerprint: str
) -> None:
    """Gate R-D construction on completed repair + validation lineage."""
    if repair_decision not in _REPAIR_LINEAGE_DECISIONS:
        raise LineageError(
            "R-D requires a completed repair attempt with decision in "
            f"{sorted(_REPAIR_LINEAGE_DECISIONS)}; got {repair_decision!r}. "
            "FAILED repairs never produce repaired evaluations."
        )
    if not isinstance(validation_fingerprint, str) or (
        not validation_fingerprint.strip() or validation_fingerprint == "none"
    ):
        raise LineageError(
            "R-D requires a real validation fingerprint; "
            f"got {validation_fingerprint!r}"
        )


def require_rh_lineage(repaired_identity: str, repair_fingerprint: str) -> None:
    """Gate R-H construction on R-D and a valid repaired identity."""
    for field_name, value in (
        ("repaired_identity", repaired_identity),
        ("repair_fingerprint", repair_fingerprint),
    ):
        if (
            not isinstance(value, str)
            or not value.strip()
            or value == "none"
        ):
            raise LineageError(
                f"R-H requires a valid {field_name}; got {value!r}"
            )


def heldout_scope(
    *,
    heldout_window: Tuple[str, str],
    universe: Mapping[str, Any],
    transaction_cost_bps: float,
    initial_cash: float,
    strict_pit: bool,
    vintage_policy: str,
    environment_fingerprint: str,
) -> Dict[str, Any]:
    """The frozen held-out scope N-H and R-H must share exactly."""
    return {
        "heldout_window": [str(heldout_window[0]), str(heldout_window[1])],
        "universe": {
            asset: sorted(instruments)
            for asset, instruments in dict(universe).items()
        },
        "transaction_cost_bps": float(transaction_cost_bps),
        "initial_cash": float(initial_cash),
        "strict_pit": bool(strict_pit),
        "vintage_policy": str(vintage_policy),
        "environment_fingerprint": str(environment_fingerprint),
    }


def assert_same_scope(first: Mapping[str, Any], second: Mapping[str, Any]) -> None:
    """Fail closed unless two held-out scopes are exactly equal.

    Comparison is canonical (frozen form on both sides) so that
    list/tuple representation differences can never pass or fail
    the check spuriously.
    """
    if freeze(dict(first)) != freeze(dict(second)):
        raise LineageError(
            "held-out scope mismatch between original and repaired "
            "evaluations: failing closed. Only agent lineage may differ."
        )


@dataclass(frozen=True)
class SealedBaseline:
    """Immutable sealed N-H original held-out baseline.

    Only ``scope``, ``scope_fingerprint``, and ``baseline_fingerprint``
    are readable before release (lineage/scope gating needs them).
    Scientific contents are unreadable until exactly one in-assembly
    release whose integrity is verified first.
    """

    scope: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    scope_fingerprint: str = ""
    baseline_fingerprint: str = ""
    payload: Optional[BaselineResult] = None
    seal_fingerprint: str = ""
    released: bool = False
    release_note: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, Mapping) or not dict(self.scope):
            raise ValueError("scope must be a non-empty mapping")
        object.__setattr__(self, "scope", freeze(dict(self.scope)))
        for field_name in (
            "scope_fingerprint",
            "baseline_fingerprint",
            "seal_fingerprint",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        if self.payload is not None and not isinstance(
            self.payload, BaselineResult
        ):
            raise TypeError(
                "payload must be a BaselineResult or None, "
                f"got {type(self.payload).__name__}"
            )
        if not isinstance(self.released, bool):
            raise TypeError("released must be a bool")
        if self.released and (
            not isinstance(self.release_note, str)
            or not self.release_note.strip()
        ):
            raise ValueError(
                "a released seal must carry a release note"
            )
        if not self.released and self.release_note is not None:
            raise ValueError(
                "an unreleased seal must not carry a release note"
            )

    @classmethod
    def seal(
        cls, *, payload: BaselineResult, scope: Mapping[str, Any]
    ) -> "SealedBaseline":
        """Seal a held-out baseline result at Phase A completion."""
        if not isinstance(payload, BaselineResult):
            raise TypeError(
                "payload must be a BaselineResult, "
                f"got {type(payload).__name__}"
            )
        scope_dict = dict(scope)
        return cls(
            scope=scope_dict,
            scope_fingerprint=fingerprint_of_dict(scope_dict),
            baseline_fingerprint=payload.fingerprint(),
            payload=payload,
            seal_fingerprint=payload.fingerprint(),
            released=False,
            release_note=None,
        )

    def contents(self) -> BaselineResult:
        """Read sealed contents. Raises unless released exactly once."""
        if not self.released:
            raise SealedAccessError(
                "sealed held-out contents requested before release: "
                "diagnosis, repair, validation, and stopping never "
                "receive them"
            )
        assert self.payload is not None
        return self.payload

    def release(self, *, phase: str) -> "SealedBaseline":
        """Release exactly once, only during final assembly, verified."""
        if self.released:
            raise SealIntegrityError(
                "double release of the held-out seal is forbidden"
            )
        if phase != ASSEMBLY_PHASE:
            raise SealIntegrityError(
                f"seal release requires phase {ASSEMBLY_PHASE!r}, "
                f"got {phase!r}"
            )
        if self.payload is None:
            raise SealIntegrityError("seal carries no payload")
        if self.payload.fingerprint() != self.seal_fingerprint:
            raise SealIntegrityError(
                "seal fingerprint mismatch: payload was corrupted or "
                "tampered with after sealing"
            )
        if self.payload.fingerprint() != self.baseline_fingerprint:
            raise SealIntegrityError(
                "baseline fingerprint mismatch on release"
            )
        return SealedBaseline(
            scope=dict(self.scope),
            scope_fingerprint=self.scope_fingerprint,
            baseline_fingerprint=self.baseline_fingerprint,
            payload=self.payload,
            seal_fingerprint=self.seal_fingerprint,
            released=True,
            release_note=(
                f"released once during {ASSEMBLY_PHASE}; seal verified"
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": thaw(self.scope),
            "scope_fingerprint": self.scope_fingerprint,
            "baseline_fingerprint": self.baseline_fingerprint,
            "payload": (
                self.payload.to_dict() if self.payload is not None else None
            ),
            "seal_fingerprint": self.seal_fingerprint,
            "released": self.released,
            "release_note": self.release_note,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SealedBaseline":
        if not isinstance(payload, Mapping):
            raise TypeError("SealedBaseline payload must be a mapping")
        known = {
            "scope", "scope_fingerprint", "baseline_fingerprint",
            "payload", "seal_fingerprint", "released",
            "release_note",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown SealedBaseline fields: {sorted(extra)}"
            )
        try:
            stored = payload["payload"]
            return cls(
                scope=dict(payload["scope"]),
                scope_fingerprint=payload["scope_fingerprint"],
                baseline_fingerprint=payload["baseline_fingerprint"],
                payload=(
                    BaselineResult.from_dict(stored)
                    if stored is not None
                    else None
                ),
                seal_fingerprint=payload["seal_fingerprint"],
                released=payload.get("released", False),
                release_note=payload.get("release_note"),
            )
        except KeyError as exc:
            raise ValueError(
                f"SealedBaseline payload missing {exc}"
            ) from exc
