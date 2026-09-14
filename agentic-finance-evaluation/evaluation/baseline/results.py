"""Baseline evaluation result artefact (E1).

``BaselineResult`` is the canonical, deterministic owner of one baseline
run::

    BaselineResult
    |-- decision_records   (the raw trajectory; canonical owner)
    |-- metrics            (pure derivations from the records)
    |-- evidence           (selected metrics as BehavioralEvidence)
    |-- evaluation_state   (populated E0 accumulator: baseline evidence,
                            budget, stopping reason)

``DecisionRecord`` objects are deliberately NOT added to the frozen E0
``EvaluationState`` (which has no records slot and must not change).
``BehavioralEvidence`` items reference records by fingerprint, so the
trajectory stays linked without duplication.

The result is frozen, serializable (``to_dict``/``from_dict`` round-trip),
and fingerprinted over its full content. No wall-clock timestamp enters
the fingerprinted payload.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.baseline.config import BaselineConfig
from evaluation.baseline.metrics import MetricResult
from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.decision_record import DecisionRecord
from evaluation.contracts.evaluation_state import EvaluationState
from evaluation.contracts.evidence import BehavioralEvidence
from evaluation.contracts.fingerprints import fingerprint_of_dict, freeze, thaw
from evaluation.contracts.stopping import StoppingReason

BUDGET_DIMENSIONS = (
    "episodes",
    "tests",
    "repairs",
    "validation_runs",
    "runtime_s",
)


@dataclass(frozen=True)
class BaselineResult:
    """One complete, immutable baseline evaluation artefact."""

    evaluation_id: str
    agent_identity: AgentIdentity
    environment_spec: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    config: BaselineConfig = None  # type: ignore[assignment]
    decision_records: Tuple[DecisionRecord, ...] = field(default_factory=tuple)
    metrics: Tuple[MetricResult, ...] = field(default_factory=tuple)
    evidence: Tuple[BehavioralEvidence, ...] = field(default_factory=tuple)
    evaluation_state: EvaluationState = None  # type: ignore[assignment]
    stopping_reason: Optional[StoppingReason] = None
    budget_usage: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if not isinstance(self.evaluation_id, str) or not self.evaluation_id.strip():
            raise ValueError("evaluation_id must be a non-empty string")
        if not isinstance(self.agent_identity, AgentIdentity):
            raise TypeError("agent_identity must be an AgentIdentity")
        if not isinstance(self.environment_spec, Mapping):
            raise TypeError("environment_spec must be a mapping")
        object.__setattr__(
            self, "environment_spec", freeze(dict(self.environment_spec))
        )
        if not isinstance(self.config, BaselineConfig):
            raise TypeError("config must be a BaselineConfig")
        records = self.decision_records
        if isinstance(records, str) or not isinstance(records, (tuple, list)):
            raise TypeError("decision_records must be a tuple/list")
        records = tuple(records)
        if not records:
            raise ValueError(
                "a baseline result over zero decisions is a contradiction; "
                "records must be non-empty"
            )
        for record in records:
            if not isinstance(record, DecisionRecord):
                raise TypeError(
                    "decision_records must contain DecisionRecord, "
                    f"got {type(record).__name__}"
                )
        object.__setattr__(self, "decision_records", records)
        metrics = self.metrics
        if isinstance(metrics, str) or not isinstance(metrics, (tuple, list)):
            raise TypeError("metrics must be a tuple/list")
        metrics = tuple(metrics)
        for metric in metrics:
            if not isinstance(metric, MetricResult):
                raise TypeError(
                    "metrics must contain MetricResult, "
                    f"got {type(metric).__name__}"
                )
        object.__setattr__(self, "metrics", metrics)
        evidence = self.evidence
        if isinstance(evidence, str) or not isinstance(evidence, (tuple, list)):
            raise TypeError("evidence must be a tuple/list")
        evidence = tuple(evidence)
        for item in evidence:
            if not isinstance(item, BehavioralEvidence):
                raise TypeError(
                    "evidence must contain BehavioralEvidence, "
                    f"got {type(item).__name__}"
                )
        object.__setattr__(self, "evidence", evidence)
        if not isinstance(self.evaluation_state, EvaluationState):
            raise TypeError("evaluation_state must be an EvaluationState")
        if self.stopping_reason is not None and not isinstance(
            self.stopping_reason, StoppingReason
        ):
            raise TypeError(
                "stopping_reason must be a StoppingReason or None, "
                f"got {self.stopping_reason!r}"
            )
        object.__setattr__(
            self, "budget_usage", freeze(self._checked_budget_usage())
        )

    def _checked_budget_usage(self) -> Dict[str, int]:
        usage = self.budget_usage
        if not isinstance(usage, Mapping):
            raise TypeError("budget_usage must be a mapping")
        checked: Dict[str, int] = {}
        for key, count in usage.items():
            if key not in BUDGET_DIMENSIONS:
                raise ValueError(f"unknown budget dimension {key!r}")
            if isinstance(count, bool) or not isinstance(count, int):
                raise TypeError(
                    f"budget_usage[{key!r}] must be an int, got {count!r}"
                )
            if count < 0:
                raise ValueError(f"budget_usage[{key!r}] must be non-negative")
            checked[key] = count
        if checked.get("episodes", 0) < 1:
            raise ValueError(
                "a completed baseline run consumes exactly one episode"
            )
        return checked

    def metric(self, name: str) -> MetricResult:
        """Fetch one metric by name; raises ``KeyError`` when absent."""
        for metric in self.metrics:
            if metric.name == name:
                return metric
        raise KeyError(f"no baseline metric {name!r}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "agent_identity": self.agent_identity.to_dict(),
            "environment_spec": thaw(self.environment_spec),
            "config": self.config.to_dict(),
            "decision_records": [r.to_dict() for r in self.decision_records],
            "metrics": [m.to_dict() for m in self.metrics],
            "evidence": [e.to_dict() for e in self.evidence],
            "evaluation_state": self.evaluation_state.to_dict(),
            "stopping_reason": (
                self.stopping_reason.value
                if self.stopping_reason is not None
                else None
            ),
            "budget_usage": thaw(self.budget_usage),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BaselineResult":
        if not isinstance(payload, Mapping):
            raise TypeError("BaselineResult payload must be a mapping")
        known = {
            "evaluation_id", "agent_identity", "environment_spec",
            "config", "decision_records", "metrics", "evidence",
            "evaluation_state", "stopping_reason", "budget_usage",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(f"unknown BaselineResult fields: {sorted(extra)}")
        try:
            stopping = payload.get("stopping_reason")
            return cls(
                evaluation_id=payload["evaluation_id"],
                agent_identity=AgentIdentity.from_dict(
                    payload["agent_identity"]
                ),
                environment_spec=dict(payload.get("environment_spec", {})),
                config=BaselineConfig.from_dict(payload["config"]),
                decision_records=tuple(
                    DecisionRecord.from_dict(item)
                    for item in payload.get("decision_records", ())
                ),
                metrics=tuple(
                    MetricResult.from_dict(item)
                    for item in payload.get("metrics", ())
                ),
                evidence=tuple(
                    BehavioralEvidence.from_dict(item)
                    for item in payload.get("evidence", ())
                ),
                evaluation_state=EvaluationState.from_dict(
                    payload["evaluation_state"]
                ),
                stopping_reason=(
                    StoppingReason.from_str(stopping)
                    if stopping is not None
                    else None
                ),
                budget_usage=dict(payload.get("budget_usage", {})),
            )
        except KeyError as exc:
            raise ValueError(
                f"BaselineResult payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        """Deterministic identity over the complete artefact (no exclusions;
        the result stores no wall-clock timestamps)."""
        return fingerprint_of_dict(self.to_dict())

    def __repr__(self) -> str:
        return (
            f"BaselineResult(evaluation_id={self.evaluation_id!r}, "
            f"agent={self.agent_identity}, "
            f"records={len(self.decision_records)}, "
            f"metrics={len(self.metrics)}, "
            f"evidence={len(self.evidence)}, "
            f"stopping={self.stopping_reason})"
        )
