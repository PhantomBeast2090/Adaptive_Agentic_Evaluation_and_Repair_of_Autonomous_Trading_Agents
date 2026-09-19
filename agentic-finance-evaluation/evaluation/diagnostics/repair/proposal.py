"""Immutable repair proposal contract (E2-F).

A ``RepairProposal`` names one constrained repair attempt against one
diagnosed hypothesis: what failed, what evidence grounds the claim,
which agent state is targeted, what should move, how, and under which
method version. It authorises nothing by itself — application,
validation, and the accept/reject decision are separate, independently
checkable steps.

The proposal binds to an exact target-agent state via
``target_agent_fingerprint``: a proposal generated for one agent state
cannot be silently applied to another.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Tuple

from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.fingerprints import fingerprint_of_dict, freeze, thaw
from evaluation.diagnostics.contracts.predictions import ExpectedDirection


@dataclass(frozen=True)
class RepairProposal:
    """One immutable, fingerprintable repair attempt specification."""

    repair_id: str
    diagnostic_id: str
    baseline_evaluation_id: str
    baseline_fingerprint: str
    diagnostic_state_fingerprint: str
    target_agent_identity: AgentIdentity
    target_agent_fingerprint: str
    hypothesis_id: str
    hypothesis_fingerprint: str
    failure_class: str
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    target_metric: str = ""
    target_direction: ExpectedDirection = ExpectedDirection.DECREASE
    method: str = ""
    method_version: str = ""
    parameters: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    rationale: str = ""
    provenance: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        for field_name in (
            "repair_id",
            "diagnostic_id",
            "baseline_evaluation_id",
            "baseline_fingerprint",
            "diagnostic_state_fingerprint",
            "target_agent_fingerprint",
            "hypothesis_id",
            "hypothesis_fingerprint",
            "failure_class",
            "target_metric",
            "rationale",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        if not isinstance(self.target_agent_identity, AgentIdentity):
            raise TypeError(
                "target_agent_identity must be an AgentIdentity, "
                f"got {type(self.target_agent_identity).__name__}"
            )
        refs = self.evidence_refs
        if isinstance(refs, str) or not isinstance(refs, (tuple, list)):
            raise TypeError("evidence_refs must be a tuple/list of strings")
        refs = tuple(refs)
        if not refs:
            raise ValueError("evidence_refs must be non-empty")
        for ref in refs:
            if not isinstance(ref, str) or not ref:
                raise ValueError(
                    "evidence_refs entries must be non-empty strings"
                )
        if len(set(refs)) != len(refs):
            raise ValueError("evidence_refs must not contain duplicates")
        object.__setattr__(self, "evidence_refs", refs)
        direction = self.target_direction
        if isinstance(direction, str) and not isinstance(
            direction, ExpectedDirection
        ):
            direction = ExpectedDirection.from_str(direction)
        if not isinstance(direction, ExpectedDirection):
            raise TypeError(
                "target_direction must be an ExpectedDirection member, "
                f"got {self.target_direction!r}"
            )
        if direction is ExpectedDirection.NO_CHANGE:
            raise ValueError(
                "target_direction must be INCREASE or DECREASE: a repair "
                "must aim to move its target metric"
            )
        object.__setattr__(self, "target_direction", direction)
        for field_name in ("method", "method_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        if not isinstance(self.parameters, Mapping):
            raise TypeError("parameters must be a mapping")
        object.__setattr__(self, "parameters", freeze(dict(self.parameters)))
        if not isinstance(self.provenance, Mapping):
            raise TypeError("provenance must be a mapping")
        object.__setattr__(self, "provenance", freeze(dict(self.provenance)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repair_id": self.repair_id,
            "diagnostic_id": self.diagnostic_id,
            "baseline_evaluation_id": self.baseline_evaluation_id,
            "baseline_fingerprint": self.baseline_fingerprint,
            "diagnostic_state_fingerprint": self.diagnostic_state_fingerprint,
            "target_agent_identity": self.target_agent_identity.to_dict(),
            "target_agent_fingerprint": self.target_agent_fingerprint,
            "hypothesis_id": self.hypothesis_id,
            "hypothesis_fingerprint": self.hypothesis_fingerprint,
            "failure_class": self.failure_class,
            "evidence_refs": list(self.evidence_refs),
            "target_metric": self.target_metric,
            "target_direction": self.target_direction.value,
            "method": self.method,
            "method_version": self.method_version,
            "parameters": thaw(self.parameters),
            "rationale": self.rationale,
            "provenance": thaw(self.provenance),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RepairProposal":
        if not isinstance(payload, Mapping):
            raise TypeError("RepairProposal payload must be a mapping")
        known = {
            "repair_id", "diagnostic_id", "baseline_evaluation_id",
            "baseline_fingerprint", "diagnostic_state_fingerprint",
            "target_agent_identity", "target_agent_fingerprint",
            "hypothesis_id", "hypothesis_fingerprint", "failure_class",
            "evidence_refs", "target_metric", "target_direction",
            "method", "method_version", "parameters", "rationale",
            "provenance",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown RepairProposal fields: {sorted(extra)}"
            )
        try:
            return cls(
                repair_id=payload["repair_id"],
                diagnostic_id=payload["diagnostic_id"],
                baseline_evaluation_id=payload["baseline_evaluation_id"],
                baseline_fingerprint=payload["baseline_fingerprint"],
                diagnostic_state_fingerprint=payload[
                    "diagnostic_state_fingerprint"
                ],
                target_agent_identity=AgentIdentity.from_dict(
                    payload["target_agent_identity"]
                ),
                target_agent_fingerprint=payload["target_agent_fingerprint"],
                hypothesis_id=payload["hypothesis_id"],
                hypothesis_fingerprint=payload["hypothesis_fingerprint"],
                failure_class=payload["failure_class"],
                evidence_refs=tuple(payload.get("evidence_refs", ())),
                target_metric=payload["target_metric"],
                target_direction=payload["target_direction"],
                method=payload["method"],
                method_version=payload["method_version"],
                parameters=dict(payload.get("parameters", {})),
                rationale=payload["rationale"],
                provenance=dict(payload.get("provenance", {})),
            )
        except KeyError as exc:
            raise ValueError(
                f"RepairProposal payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        """Deterministic identity over every proposal field."""
        return fingerprint_of_dict(self.to_dict())
