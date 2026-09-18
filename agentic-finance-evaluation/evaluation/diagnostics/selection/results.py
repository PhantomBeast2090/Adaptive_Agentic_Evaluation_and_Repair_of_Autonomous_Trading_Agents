"""Terminal selection outcome when no candidate can be proposed (E2-D).

``NoCandidateResult`` is a frozen, fingerprinted value — not an
exception — so loop drivers can branch on it without try/except control
flow. ``suggested_stopping`` names a frozen E0 vocabulary member for the
driver's consideration; the selector never sets stopping state itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from evaluation.contracts.fingerprints import fingerprint_of_dict
from evaluation.contracts.stopping import StoppingReason


@dataclass(frozen=True)
class NoCandidateResult:
    """Structured record that selection produced no proposal."""

    diagnostic_id: str
    reason: str
    suggested_stopping: Optional[StoppingReason] = None
    candidates_considered: int = 0
    method: str = ""
    version: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.diagnostic_id, str) or not self.diagnostic_id.strip():
            raise ValueError("diagnostic_id must be a non-empty string")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must be a non-empty string")
        if self.suggested_stopping is not None and not isinstance(
            self.suggested_stopping, StoppingReason
        ):
            raise TypeError(
                "suggested_stopping must be a StoppingReason or None, "
                f"got {self.suggested_stopping!r}"
            )
        if (
            isinstance(self.candidates_considered, bool)
            or not isinstance(self.candidates_considered, int)
            or self.candidates_considered < 0
        ):
            raise ValueError("candidates_considered must be a non-negative int")
        for field_name in ("method", "version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "diagnostic_id": self.diagnostic_id,
            "reason": self.reason,
            "suggested_stopping": (
                self.suggested_stopping.value
                if self.suggested_stopping is not None
                else None
            ),
            "candidates_considered": self.candidates_considered,
            "method": self.method,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "NoCandidateResult":
        if not isinstance(payload, Mapping):
            raise TypeError("NoCandidateResult payload must be a mapping")
        known = {
            "diagnostic_id", "reason", "suggested_stopping",
            "candidates_considered", "method", "version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown NoCandidateResult fields: {sorted(extra)}"
            )
        try:
            suggested = payload.get("suggested_stopping")
            return cls(
                diagnostic_id=payload["diagnostic_id"],
                reason=payload["reason"],
                suggested_stopping=(
                    StoppingReason.from_str(suggested)
                    if suggested is not None
                    else None
                ),
                candidates_considered=payload.get("candidates_considered", 0),
                method=payload["method"],
                version=payload["version"],
            )
        except KeyError as exc:
            raise ValueError(
                f"NoCandidateResult payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        """Deterministic identity over every outcome field."""
        return fingerprint_of_dict(self.to_dict())
