"""Consistency dimension evaluator.

Evaluates consistency via trajectory determinism across replications. Does not
invent consistency scores; relies on actual repeated runs with identical configs.
"""

from typing import Any, Dict, List

from evaluation.evaluators.static.base import StaticDimensionEvaluator
from src.schemas.static_evaluation import FailureRecord


class ConsistencyEvaluator(StaticDimensionEvaluator):
    """Evaluates consistency dimension.

    Consistency is checked via trajectory content digests: identical agent + scenario
    + seed should produce identical trajectory digests. This evaluator does not score
    a single trajectory; it requires comparison data.

    For Phase 2 static evaluation, consistency is measured by rerunning episodes with
    the same configuration and verifying digest equality. Within-episode repeatability
    is also measured but is typically undefined (observations rarely repeat exactly in
    historical replay).
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("consistency", config)
        self.min_repeatability = config.get("min_action_repeatability")

    def evaluate(
        self,
        trajectory,
        metrics: Dict[str, Any],
        episode_id: str,
        scenario_id: str,
    ) -> List[FailureRecord]:
        failures = []

        # Action repeatability (within-episode consistency)
        # This is typically None for historical replay (observations don't repeat),
        # but if it IS defined and below threshold, that's evidence of inconsistency.
        if self.min_repeatability is not None:
            repeatability = metrics.get("action_repeatability")
            if repeatability is not None and repeatability < self.min_repeatability:
                failures.append(
                    self._failure(
                        metric_name="action_repeatability",
                        observed_value=repeatability,
                        threshold=self.min_repeatability,
                        threshold_direction="below",
                        episode_id=episode_id,
                        scenario_id=scenario_id,
                        severity="medium",
                        evidence=f"Action repeatability {repeatability:.4f} below threshold {self.min_repeatability} (inconsistent actions on repeated observations)",
                    )
                )

        # Cross-replication determinism is checked at the orchestrator level by
        # comparing trajectory digests, not within a single episode evaluation.

        return failures
