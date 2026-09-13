"""Explicit evaluator termination states (E0 contract).

E0 defines the vocabulary only. No stopping policy or stopping logic lives
here; the future adaptive loop (E2) will decide *when* to stop, using these
values to record *why* it stopped.
"""

from __future__ import annotations

from enum import Enum


class StoppingReason(str, Enum):
    """Closed vocabulary of evaluation termination states."""

    SUCCESS_CONFIDENT = "SUCCESS_CONFIDENT"
    NO_ACTIONABLE_FAILURE = "NO_ACTIONABLE_FAILURE"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    HYPOTHESIS_UNRESOLVED = "HYPOTHESIS_UNRESOLVED"
    REPAIR_FAILED = "REPAIR_FAILED"
    REGRESSION_DETECTED = "REGRESSION_DETECTED"

    def to_str(self) -> str:
        """Serialize to its plain string value."""
        return self.value

    @classmethod
    def from_str(cls, value: object) -> "StoppingReason":
        """Parse a string back into a member; fail closed on anything else.

        Raises:
            ValueError: if ``value`` is not one of the six known members.
                Unknown reasons are never coerced to a default.
        """
        for member in cls:
            if value == member.value:
                return member
        known = sorted(member.value for member in cls)
        raise ValueError(f"unknown StoppingReason {value!r}; known: {known}")
