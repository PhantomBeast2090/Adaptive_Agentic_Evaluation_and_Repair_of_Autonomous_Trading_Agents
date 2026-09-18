"""Interpretation record: frozen handle for one interpret() call (E2-C).

An ``InterpretationRecord`` names everything one interpretation produced —
the updates created and the uncertainty snapshot recorded — by id, so the
future diagnostic loop (E2-D) has a stable, fingerprinted handle without
re-reading the whole state. Like every E2-C artefact it carries method and
version, serialises deterministically, and contains no wall-clock data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Tuple

from evaluation.contracts.fingerprints import fingerprint_of_dict


@dataclass(frozen=True)
class InterpretationRecord:
    """Immutable handle for one completed interpretation."""

    interpretation_id: str
    diagnostic_id: str
    result_id: str
    prediction_ids: Tuple[str, ...] = field(default_factory=tuple)
    update_ids: Tuple[str, ...] = field(default_factory=tuple)
    uncertainty_id: str = ""
    method: str = ""
    version: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "interpretation_id",
            "diagnostic_id",
            "result_id",
            "uncertainty_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        for field_name in ("prediction_ids", "update_ids"):
            value = getattr(self, field_name)
            if isinstance(value, str) or not isinstance(value, (tuple, list)):
                raise TypeError(
                    f"{field_name} must be a tuple/list of strings"
                )
            items = tuple(value)
            for item in items:
                if not isinstance(item, str) or not item:
                    raise ValueError(
                        f"{field_name} entries must be non-empty strings"
                    )
            if len(set(items)) != len(items):
                raise ValueError(
                    f"{field_name} must not contain duplicates"
                )
            object.__setattr__(self, field_name, items)
        if not self.prediction_ids:
            raise ValueError("prediction_ids must be non-empty")
        if len(self.prediction_ids) != len(self.update_ids):
            raise ValueError(
                "update_ids must align one-to-one with prediction_ids"
            )
        for field_name in ("method", "version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interpretation_id": self.interpretation_id,
            "diagnostic_id": self.diagnostic_id,
            "result_id": self.result_id,
            "prediction_ids": list(self.prediction_ids),
            "update_ids": list(self.update_ids),
            "uncertainty_id": self.uncertainty_id,
            "method": self.method,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InterpretationRecord":
        if not isinstance(payload, Mapping):
            raise TypeError("InterpretationRecord payload must be a mapping")
        known = {
            "interpretation_id", "diagnostic_id", "result_id",
            "prediction_ids", "update_ids", "uncertainty_id", "method",
            "version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown InterpretationRecord fields: {sorted(extra)}"
            )
        try:
            return cls(
                interpretation_id=payload["interpretation_id"],
                diagnostic_id=payload["diagnostic_id"],
                result_id=payload["result_id"],
                prediction_ids=tuple(payload.get("prediction_ids", ())),
                update_ids=tuple(payload.get("update_ids", ())),
                uncertainty_id=payload["uncertainty_id"],
                method=payload["method"],
                version=payload["version"],
            )
        except KeyError as exc:
            raise ValueError(
                f"InterpretationRecord payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        """Deterministic identity over every record field."""
        return fingerprint_of_dict(self.to_dict())
