"""Static evaluation result schemas.

These schemas represent the output of Phase 2 static evaluation: fixed scenario
sets, deterministic metrics, observed failures, and agent profiles. They are
explicitly separate from the adaptive evaluation schemas (which add diagnosis,
intervention, and dynamic scenario selection in later phases).

Every schema here is serializable, auditable, and carries the provenance needed
to reproduce the evaluation.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FailureRecord(BaseModel):
    """An observed failure on a single dimension.

    A failure is an observed violation of a threshold or constraint, not a
    diagnosed root cause. Diagnosis belongs to later phases.

    Example: `max_drawdown = 0.35` when threshold is `0.20` is an observed
    failure. It does NOT automatically imply "poor risk management" as a cause;
    that requires diagnosis.
    """

    dimension: str  # "performance", "risk", "constraint", "safety", etc.
    metric_name: str  # The specific metric that failed
    observed_value: Optional[float]  # None when the metric was undefined
    threshold: Optional[float]  # None for boolean/categorical failures
    threshold_direction: Optional[str] = None  # "above" | "below" | None
    episode_id: str
    scenario_id: str
    severity: str  # "critical" | "high" | "medium" | "low"
    evidence: str  # Human-readable description of what was observed
    timestamp: str = Field(default_factory=_utc_now_iso)


class EpisodeEvaluation(BaseModel):
    """Evaluation result for one episode across all dimensions.

    Aggregates all dimension-specific evaluations and failures for a single
    trajectory. This is the atomic evaluation unit: one agent, one scenario,
    one run.
    """

    episode_id: str
    scenario_id: str
    agent_id: str
    agent_version: str
    trajectory_digest: str  # Reproducibility fingerprint
    metrics: Dict[str, Any]  # Raw metrics from static_metrics.compute_episode_metrics
    failures: List[FailureRecord]
    dimensions_evaluated: List[str]
    dimensions_passed: List[str]
    dimensions_failed: List[str]
    timestamp: str = Field(default_factory=_utc_now_iso)


class StaticAgentProfile(BaseModel):
    """Aggregated evaluation profile for one agent across the fixed scenario set.

    Summarizes observed behaviour, failure rates, and metric distributions across
    the static baseline. This is descriptive evidence, not a fitness score.
    """

    agent_id: str
    agent_version: str
    evaluation_run_id: str
    episodes_evaluated: int
    episodes_with_failures: int
    total_failures: int
    failures_by_dimension: Dict[str, int]
    failures_by_severity: Dict[str, int]
    metric_distributions: Dict[str, Dict[str, float]]  # {metric: {min, max, mean, median, p95}}
    dimensions_evaluated: List[str]
    scenario_ids: List[str]  # Fixed set used for this baseline
    holdout_used: bool  # Must always be False for static baseline
    timestamp: str = Field(default_factory=_utc_now_iso)


class StaticEvaluationResult(BaseModel):
    """Complete result of one static evaluation run.

    Records everything needed to reproduce the experiment: configuration,
    scenario set, per-episode evaluations, agent profiles, and run manifest.

    This is the top-level artifact persisted to disk.
    """

    run_id: str
    experiment_id: str
    description: str
    agent_profiles: List[StaticAgentProfile]
    episode_evaluations: List[EpisodeEvaluation]
    scenario_ids: List[str]  # Fixed set, deterministically ordered
    scenario_source_splits: List[str]  # Data provenance
    holdout_scenario_ids: List[str]  # Recorded but never used for baseline scoring
    configuration: Dict[str, Any]  # Evaluation config snapshot
    total_episodes: int
    total_failures: int
    dimensions: List[str]
    started_at: str
    completed_at: str = Field(default_factory=_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary for JSON/JSONL output."""
        return self.model_dump()
