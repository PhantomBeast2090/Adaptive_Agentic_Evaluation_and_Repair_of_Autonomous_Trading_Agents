"""Pure directional comparison for committed predictions (E2-C).

:func:`compare` adjudicates one (direction, observed, control) triple
under ``directional-band v1`` (see ``methodology.py``). It is a pure
function of its inputs: no state, no I/O, no randomness, no clock.

Inputs may be absent on either side:

* observed ``None`` (metric missing from the diagnostic result, or
  explicitly undefined there) → ``INCONCLUSIVE``;
* control ``None`` (metric absent from the baseline artefact, or
  explicitly undefined there) → ``INCONCLUSIVE`` with the control's
  recorded reason carried through.

The ``expected_magnitude`` free-text field of a prediction is never
parsed here: it is rationale, not a number. Numeric adjudication uses
only observed and control values plus the methodology band.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from evaluation.diagnostics.contracts.hypothesis_updates import Compatibility
from evaluation.diagnostics.contracts.predictions import ExpectedDirection
from evaluation.diagnostics.interpretation.methodology import TAU


@dataclass(frozen=True)
class Comparison:
    """Outcome of one directional comparison, with its numeric detail."""

    compatibility: Compatibility
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.compatibility, Compatibility):
            raise TypeError(
                "compatibility must be a Compatibility member, "
                f"got {self.compatibility!r}"
            )
        if not isinstance(self.detail, str) or not self.detail.strip():
            raise ValueError("detail must be a non-empty string")


def _number(value: object, field_name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or value != value
        or value in (float("inf"), float("-inf"))
    ):
        raise TypeError(f"{field_name} must be a finite number or None")
    return float(value)


def compare(
    *,
    direction: ExpectedDirection,
    observed_value: Optional[float],
    control_value: Optional[float],
    control_reason: str = "",
) -> Comparison:
    """Adjudicate one directional claim against one control value."""
    if not isinstance(direction, ExpectedDirection):
        raise TypeError(
            "direction must be an ExpectedDirection member, "
            f"got {direction!r}"
        )
    if observed_value is not None:
        observed_value = _number(observed_value, "observed_value")
    if control_value is not None:
        control_value = _number(control_value, "control_value")
    if observed_value is None:
        return Comparison(
            Compatibility.INCONCLUSIVE,
            "observed value absent from diagnostic result",
        )
    if control_value is None:
        if not isinstance(control_reason, str) or not control_reason.strip():
            raise ValueError(
                "control_reason must be non-empty when control is unavailable"
            )
        return Comparison(
            Compatibility.INCONCLUSIVE,
            f"control unavailable: {control_reason}",
        )
    obs = observed_value
    base = control_value
    if base == 0.0:
        if direction is ExpectedDirection.INCREASE:
            matched = obs > 0.0
        elif direction is ExpectedDirection.DECREASE:
            matched = obs < 0.0
        else:
            matched = obs == 0.0
        detail = f"obs={obs!r} control=0.0 (exact-zero rule)"
    else:
        rel = (obs - base) / abs(base)
        if direction is ExpectedDirection.INCREASE:
            matched = rel > TAU
        elif direction is ExpectedDirection.DECREASE:
            matched = rel < -TAU
        else:
            matched = abs(rel) <= TAU
        detail = f"obs={obs!r} control={base!r} rel_change={rel:+.6f} band={TAU}"
    if matched:
        return Comparison(Compatibility.SUPPORTS, detail)
    return Comparison(Compatibility.CONTRADICTS, detail)
