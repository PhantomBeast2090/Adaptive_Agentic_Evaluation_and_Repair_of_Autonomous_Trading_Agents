"""DiagnosticTest: first-class diagnostic intervention descriptor (E0).

A diagnostic test names a targeted intervention (information hiding/delay,
cost shifts, regime changes — described, not executed), the failure
classes it discriminates between, what it will measure, what
discrimination is expected, what it costs, and what must hold before it
may run.

E0 defines what a test *is*. No intervention is implemented here, no
selector lives here (E2), and no test is executed here. The fingerprint
covers **every** field including the human-readable ``description``: a
description can encode experimental semantics, so a semantic change must
change identity. If commentary that is intentionally excluded from
identity is ever needed, it must be an explicit separate metadata field,
not a silent fingerprint exclusion.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Tuple

from evaluation.contracts.fingerprints import fingerprint_of_dict, freeze, thaw


@dataclass(frozen=True)
class DiagnosticTest:
    """One immutable diagnostic test specification."""

    test_id: str
    description: str
    target_failure_classes: Tuple[str, ...] = field(default_factory=tuple)
    intervention: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    measures: Tuple[str, ...] = field(default_factory=tuple)
    expected_discrimination: str = ""
    estimated_cost: float = 0.0
    preconditions: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.test_id, str) or not self.test_id.strip():
            raise ValueError("test_id must be a non-empty string")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("description must be a non-empty string")
        targets = self._checked_str_tuple(
            self.target_failure_classes, "target_failure_classes"
        )
        if not targets:
            raise ValueError("target_failure_classes must be non-empty")
        object.__setattr__(self, "target_failure_classes", targets)
        if not isinstance(self.intervention, Mapping):
            raise TypeError("intervention must be a mapping")
        intervention = dict(self.intervention)
        if not intervention:
            raise ValueError("intervention must be non-empty")
        kind = intervention.get("type")
        if not isinstance(kind, str) or not kind:
            raise ValueError("intervention must carry a non-empty 'type'")
        object.__setattr__(self, "intervention", freeze(intervention))
        measures = self._checked_str_tuple(self.measures, "measures")
        if not measures:
            raise ValueError("measures must be non-empty")
        object.__setattr__(self, "measures", measures)
        if (
            not isinstance(self.expected_discrimination, str)
            or not self.expected_discrimination.strip()
        ):
            raise ValueError("expected_discrimination must be a non-empty string")
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
        object.__setattr__(
            self, "preconditions",
            self._checked_str_tuple(self.preconditions, "preconditions"),
        )

    @staticmethod
    def _checked_str_tuple(value: object, field_name: str) -> Tuple[str, ...]:
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
            "test_id": self.test_id,
            "description": self.description,
            "target_failure_classes": list(self.target_failure_classes),
            "intervention": thaw(self.intervention),
            "measures": list(self.measures),
            "expected_discrimination": self.expected_discrimination,
            "estimated_cost": self.estimated_cost,
            "preconditions": list(self.preconditions),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DiagnosticTest":
        if not isinstance(payload, Mapping):
            raise TypeError("DiagnosticTest payload must be a mapping")
        known = {
            "test_id", "description", "target_failure_classes",
            "intervention", "measures", "expected_discrimination",
            "estimated_cost", "preconditions",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown DiagnosticTest fields: {sorted(extra)}"
            )
        try:
            return cls(
                test_id=payload["test_id"],
                description=payload["description"],
                target_failure_classes=tuple(
                    payload.get("target_failure_classes", ())
                ),
                intervention=dict(payload.get("intervention", {})),
                measures=tuple(payload.get("measures", ())),
                expected_discrimination=payload.get(
                    "expected_discrimination", ""
                ),
                estimated_cost=payload.get("estimated_cost", 0.0),
                preconditions=tuple(payload.get("preconditions", ())),
            )
        except KeyError as exc:
            raise ValueError(
                f"DiagnosticTest payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        """Deterministic identity over every test field.

        All semantically relevant fields are included — ``test_id``,
        ``description``, ``target_failure_classes``, ``intervention``,
        ``measures``, ``expected_discrimination``, ``estimated_cost``,
        ``preconditions``. Nothing is silently excluded.
        """
        return fingerprint_of_dict(self.to_dict())
