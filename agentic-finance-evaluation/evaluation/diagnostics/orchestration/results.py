"""Closed-loop orchestration result artefact (E2-E).

``OrchestrationResult`` is the frozen canonical record of one diagnostic
loop run: the ordered iteration trace, the terminal outcome, the final
state fingerprint, and the identities that make the run reproducible.
Like the trace entries, it references artefacts by id and fingerprint —
``DiagnosticState`` remains the object store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.contracts.fingerprints import fingerprint_of_dict
from evaluation.contracts.stopping import StoppingReason
from evaluation.diagnostics.orchestration.trace import IterationTraceEntry


@dataclass(frozen=True)
class OrchestrationResult:
    """One complete, immutable closed-loop diagnosis record."""

    diagnostic_id: str
    baseline_evaluation_id: str
    baseline_fingerprint: str
    config_fingerprint: str
    iterations: Tuple[IterationTraceEntry, ...] = field(default_factory=tuple)
    terminal_condition: str = ""
    stopping_reason: Optional[StoppingReason] = None
    no_candidate_reason: Optional[str] = None
    final_state_fingerprint: str = ""
    method: str = ""
    version: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "diagnostic_id",
            "baseline_evaluation_id",
            "baseline_fingerprint",
            "config_fingerprint",
            "terminal_condition",
            "final_state_fingerprint",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        iterations = self.iterations
        if isinstance(iterations, str) or not isinstance(
            iterations, (tuple, list)
        ):
            raise TypeError(
                "iterations must be a tuple/list of IterationTraceEntry"
            )
        iterations = tuple(iterations)
        for entry in iterations:
            if not isinstance(entry, IterationTraceEntry):
                raise TypeError(
                    "iterations must contain IterationTraceEntry, "
                    f"got {type(entry).__name__}"
                )
        indices = [entry.iteration_index for entry in iterations]
        if indices != list(range(len(iterations))):
            raise ValueError(
                "iteration indices must be dense from zero in order"
            )
        object.__setattr__(self, "iterations", iterations)
        if self.stopping_reason is not None and not isinstance(
            self.stopping_reason, StoppingReason
        ):
            raise TypeError(
                "stopping_reason must be a StoppingReason or None, "
                f"got {self.stopping_reason!r}"
            )
        if self.no_candidate_reason is not None and (
            not isinstance(self.no_candidate_reason, str)
            or not self.no_candidate_reason.strip()
        ):
            raise ValueError(
                "no_candidate_reason must be a non-empty string or None"
            )
        for field_name in ("method", "version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "diagnostic_id": self.diagnostic_id,
            "baseline_evaluation_id": self.baseline_evaluation_id,
            "baseline_fingerprint": self.baseline_fingerprint,
            "config_fingerprint": self.config_fingerprint,
            "iterations": [entry.to_dict() for entry in self.iterations],
            "terminal_condition": self.terminal_condition,
            "stopping_reason": (
                self.stopping_reason.value
                if self.stopping_reason is not None
                else None
            ),
            "no_candidate_reason": self.no_candidate_reason,
            "final_state_fingerprint": self.final_state_fingerprint,
            "method": self.method,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OrchestrationResult":
        if not isinstance(payload, Mapping):
            raise TypeError("OrchestrationResult payload must be a mapping")
        known = {
            "diagnostic_id", "baseline_evaluation_id",
            "baseline_fingerprint", "config_fingerprint", "iterations",
            "terminal_condition", "stopping_reason", "no_candidate_reason",
            "final_state_fingerprint", "method", "version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown OrchestrationResult fields: {sorted(extra)}"
            )
        try:
            stopping = payload.get("stopping_reason")
            return cls(
                diagnostic_id=payload["diagnostic_id"],
                baseline_evaluation_id=payload["baseline_evaluation_id"],
                baseline_fingerprint=payload["baseline_fingerprint"],
                config_fingerprint=payload["config_fingerprint"],
                iterations=tuple(
                    IterationTraceEntry.from_dict(item)
                    for item in payload.get("iterations", ())
                ),
                terminal_condition=payload["terminal_condition"],
                stopping_reason=(
                    StoppingReason.from_str(stopping)
                    if stopping is not None
                    else None
                ),
                no_candidate_reason=payload.get("no_candidate_reason"),
                final_state_fingerprint=payload["final_state_fingerprint"],
                method=payload["method"],
                version=payload["version"],
            )
        except KeyError as exc:
            raise ValueError(
                f"OrchestrationResult payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        """Deterministic identity over the complete orchestration record."""
        return fingerprint_of_dict(self.to_dict())
