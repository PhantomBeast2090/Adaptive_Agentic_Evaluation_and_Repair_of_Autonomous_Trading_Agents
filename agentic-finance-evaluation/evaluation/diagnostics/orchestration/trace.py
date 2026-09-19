"""Iteration trace entries for closed-loop diagnosis (E2-E).

An ``IterationTraceEntry`` records one loop pass by immutable reference:
proposal, rationale, test, result, episode, interpretation, updates, and
the state fingerprints bracketing the pass. Artefacts live in
``DiagnosticState`` and the returned episode objects; the trace carries
ids and fingerprints only, so the final result stays small while every
step remains reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.contracts.fingerprints import fingerprint_of_dict


@dataclass(frozen=True)
class IterationTraceEntry:
    """One immutable record of one orchestration loop iteration."""

    iteration_index: int
    proposal_id: str
    rationale_id: str
    test_id: str
    result_id: str
    episode_id: str
    execution_fingerprint: str
    interpretation_id: Optional[str] = None
    update_ids: Tuple[str, ...] = field(default_factory=tuple)
    uncertainty_id: Optional[str] = None
    pre_state_fingerprint: str = ""
    post_state_fingerprint: str = ""
    completed: bool = True

    def __post_init__(self) -> None:
        if (
            isinstance(self.iteration_index, bool)
            or not isinstance(self.iteration_index, int)
            or self.iteration_index < 0
        ):
            raise ValueError("iteration_index must be a non-negative int")
        for field_name in (
            "proposal_id",
            "rationale_id",
            "test_id",
            "result_id",
            "episode_id",
            "execution_fingerprint",
            "pre_state_fingerprint",
            "post_state_fingerprint",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        for field_name in ("interpretation_id", "uncertainty_id"):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                raise ValueError(
                    f"{field_name} must be a non-empty string or None"
                )
        if not self.completed and (
            self.interpretation_id is not None
            or self.update_ids
            or self.uncertainty_id is not None
        ):
            raise ValueError(
                "uncompleted iterations carry no interpretation references"
            )
        update_ids = self.update_ids
        if isinstance(update_ids, str) or not isinstance(
            update_ids, (tuple, list)
        ):
            raise TypeError("update_ids must be a tuple/list of strings")
        update_ids = tuple(update_ids)
        for update_id in update_ids:
            if not isinstance(update_id, str) or not update_id.strip():
                raise ValueError(
                    "update_ids entries must be non-empty strings"
                )
        if len(set(update_ids)) != len(update_ids):
            raise ValueError("update_ids must not contain duplicates")
        object.__setattr__(self, "update_ids", update_ids)
        if not isinstance(self.completed, bool):
            raise TypeError("completed must be a bool")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration_index": self.iteration_index,
            "proposal_id": self.proposal_id,
            "rationale_id": self.rationale_id,
            "test_id": self.test_id,
            "result_id": self.result_id,
            "episode_id": self.episode_id,
            "execution_fingerprint": self.execution_fingerprint,
            "interpretation_id": self.interpretation_id,
            "update_ids": list(self.update_ids),
            "uncertainty_id": self.uncertainty_id,
            "pre_state_fingerprint": self.pre_state_fingerprint,
            "post_state_fingerprint": self.post_state_fingerprint,
            "completed": self.completed,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IterationTraceEntry":
        if not isinstance(payload, Mapping):
            raise TypeError("IterationTraceEntry payload must be a mapping")
        known = {
            "iteration_index", "proposal_id", "rationale_id", "test_id",
            "result_id", "episode_id", "execution_fingerprint",
            "interpretation_id", "update_ids", "uncertainty_id",
            "pre_state_fingerprint", "post_state_fingerprint", "completed",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown IterationTraceEntry fields: {sorted(extra)}"
            )
        try:
            return cls(
                iteration_index=payload["iteration_index"],
                proposal_id=payload["proposal_id"],
                rationale_id=payload["rationale_id"],
                test_id=payload["test_id"],
                result_id=payload["result_id"],
                episode_id=payload["episode_id"],
                execution_fingerprint=payload["execution_fingerprint"],
                interpretation_id=payload.get("interpretation_id"),
                update_ids=tuple(payload.get("update_ids", ())),
                uncertainty_id=payload.get("uncertainty_id"),
                pre_state_fingerprint=payload["pre_state_fingerprint"],
                post_state_fingerprint=payload["post_state_fingerprint"],
                completed=payload.get("completed", True),
            )
        except KeyError as exc:
            raise ValueError(
                f"IterationTraceEntry payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        """Deterministic identity over every trace field."""
        return fingerprint_of_dict(self.to_dict())
