"""Base evaluator for static evaluation dimensions.

Every dimension evaluator consumes precomputed metrics from the static metrics
layer and produces structured failure records. Evaluators interpret evidence;
they do not recompute metrics.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from src.schemas.static_evaluation import FailureRecord


class StaticDimensionEvaluator(ABC):
    """Base class for dimension-specific evaluators.

    Each evaluator examines one dimension (performance, risk, constraint, etc.)
    and produces a list of observed failures. An empty list means the dimension
    passed.
    """

    def __init__(self, dimension: str, config: Dict[str, Any]):
        self.dimension = dimension
        self.config = config

    @abstractmethod
    def evaluate(
        self,
        trajectory,
        metrics: Dict[str, Any],
        episode_id: str,
        scenario_id: str,
    ) -> List[FailureRecord]:
        """Evaluate one episode on this dimension.

        Args:
            trajectory: The recorded Trajectory object
            metrics: Precomputed metrics from static_metrics.compute_episode_metrics
            episode_id: Episode identifier for provenance
            scenario_id: Scenario identifier for provenance

        Returns:
            List of FailureRecord objects. Empty list means no failures observed.
        """
        pass

    def _failure(
        self,
        metric_name: str,
        observed_value: Any,
        threshold: Any,
        threshold_direction: str,
        episode_id: str,
        scenario_id: str,
        severity: str,
        evidence: str,
    ) -> FailureRecord:
        """Convenience helper for creating a FailureRecord."""
        return FailureRecord(
            dimension=self.dimension,
            metric_name=metric_name,
            observed_value=float(observed_value) if isinstance(observed_value, (int, float)) else None,
            threshold=float(threshold) if isinstance(threshold, (int, float)) else None,
            threshold_direction=threshold_direction,
            episode_id=episode_id,
            scenario_id=scenario_id,
            severity=severity,
            evidence=evidence,
        )
