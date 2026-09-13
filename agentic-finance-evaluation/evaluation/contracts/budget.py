"""Explicit evaluation budget limits (E0 contract).

Limits are explicit experiment policy, never hidden inside evaluator code.
``None`` means unbounded for that dimension and must be passed explicitly;
there are no silent defaults. Invalid values raise instead of being
replaced with arbitrary defaults.

E0 defines the representation and the exhaustion predicates only. Budget
*enforcement* (the loop that stops consuming) belongs to the future E2
adaptive loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from evaluation.contracts.fingerprints import fingerprint_of_dict

# Canonical usage-dimension names shared by is_exhausted/remaining.
USAGE_DIMENSIONS = (
    "episodes",
    "tests",
    "repairs",
    "validation_runs",
    "runtime_s",
)

_LIMIT_FIELDS = (
    "max_episodes",
    "max_tests",
    "max_repairs",
    "max_validation_runs",
    "max_runtime",
)

_USAGE_TO_LIMIT = {
    "episodes": "max_episodes",
    "tests": "max_tests",
    "repairs": "max_repairs",
    "validation_runs": "max_validation_runs",
    "runtime_s": "max_runtime",
}


def _check_limit(name: str, value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int or None, got {value!r}")
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value}")
    return value


@dataclass(frozen=True)
class EvaluationBudget:
    """Named, validated budget limits for one evaluation.

    All five fields are required at construction (pass ``None`` explicitly
    for an unbounded dimension). Zero is legal and means "allow none".
    """

    max_episodes: Optional[int]
    max_tests: Optional[int]
    max_repairs: Optional[int]
    max_validation_runs: Optional[int]
    max_runtime: Optional[int]

    def __post_init__(self) -> None:
        for name in _LIMIT_FIELDS:
            _check_limit(name, getattr(self, name))

    def _check_usage(self, usage: Mapping[str, Any]) -> Dict[str, int]:
        if not isinstance(usage, Mapping):
            raise TypeError("usage must be a mapping of dimension to count")
        checked: Dict[str, int] = {}
        for key, count in usage.items():
            if key not in _USAGE_TO_LIMIT:
                raise ValueError(
                    f"unknown usage dimension {key!r}; known: "
                    f"{sorted(_USAGE_TO_LIMIT)}"
                )
            if isinstance(count, bool) or not isinstance(count, int):
                raise TypeError(
                    f"usage[{key!r}] must be an int, got {count!r}"
                )
            if count < 0:
                raise ValueError(f"usage[{key!r}] must be non-negative")
            checked[key] = count
        return checked

    def is_exhausted(self, usage: Mapping[str, Any]) -> bool:
        """True when any bounded dimension has reached its limit."""
        checked = self._check_usage(usage)
        for dimension, count in checked.items():
            limit = getattr(self, _USAGE_TO_LIMIT[dimension])
            if limit is not None and count >= limit:
                return True
        return False

    def remaining(self, usage: Mapping[str, Any]) -> Dict[str, Optional[int]]:
        """Remaining allowance per dimension; ``None`` means unbounded."""
        checked = self._check_usage(usage)
        out: Dict[str, Optional[int]] = {}
        for dimension in USAGE_DIMENSIONS:
            limit = getattr(self, _USAGE_TO_LIMIT[dimension])
            if limit is None:
                out[dimension] = None
            else:
                out[dimension] = max(0, limit - checked.get(dimension, 0))
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {name: getattr(self, name) for name in _LIMIT_FIELDS}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvaluationBudget":
        if not isinstance(payload, Mapping):
            raise TypeError("EvaluationBudget payload must be a mapping")
        try:
            kwargs = {name: payload[name] for name in _LIMIT_FIELDS}
        except KeyError as exc:
            raise ValueError(f"EvaluationBudget payload missing {exc}") from exc
        extra = set(payload) - set(_LIMIT_FIELDS)
        if extra:
            raise ValueError(f"unknown EvaluationBudget fields: {sorted(extra)}")
        return cls(**kwargs)

    def fingerprint(self) -> str:
        """Deterministic identity over all five limits (None included)."""
        return fingerprint_of_dict(self.to_dict())
