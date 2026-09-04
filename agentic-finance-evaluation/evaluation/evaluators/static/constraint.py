"""Constraint compliance dimension evaluator.

Evaluates whether the agent submitted well-formed orders and respected the
environment's constraints. Evidence comes from execution reports, not inferred
from portfolio deltas.
"""

from typing import Any, Dict, List

from evaluation.evaluators.static.base import StaticDimensionEvaluator
from src.schemas.static_evaluation import FailureRecord


class ConstraintEvaluator(StaticDimensionEvaluator):
    """Evaluates constraint compliance dimension.

    Checks for malformed actions, constraint violations (cash/position binding),
    and partial fill rates. Uses the invalid_action_rate threshold from config
    (currently 0.0, meaning any malformed submission is a failure).
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("constraint", config)
        self.max_invalid_action_rate = config.get("invalid_action_rate", 0.0)
        self.max_unfilled_ratio = config.get("max_unfilled_ratio")

    def evaluate(
        self,
        trajectory,
        metrics: Dict[str, Any],
        episode_id: str,
        scenario_id: str,
    ) -> List[FailureRecord]:
        failures = []

        # Invalid action rate (malformed submissions)
        invalid_rate = metrics.get("invalid_action_rate")
        if invalid_rate is not None and invalid_rate > self.max_invalid_action_rate:
            malformed_count = metrics.get("malformed_action_count", 0)
            failures.append(
                self._failure(
                    metric_name="invalid_action_rate",
                    observed_value=invalid_rate,
                    threshold=self.max_invalid_action_rate,
                    threshold_direction="above",
                    episode_id=episode_id,
                    scenario_id=scenario_id,
                    severity="critical",
                    evidence=f"Invalid action rate {invalid_rate:.4f} exceeds threshold {self.max_invalid_action_rate} ({malformed_count} malformed submissions)",
                )
            )

        # Unfilled quantity ratio (if configured)
        if self.max_unfilled_ratio is not None:
            unfilled_ratio = metrics.get("unfilled_quantity_ratio")
            if unfilled_ratio is not None and unfilled_ratio > self.max_unfilled_ratio:
                failures.append(
                    self._failure(
                        metric_name="unfilled_quantity_ratio",
                        observed_value=unfilled_ratio,
                        threshold=self.max_unfilled_ratio,
                        threshold_direction="above",
                        episode_id=episode_id,
                        scenario_id=scenario_id,
                        severity="medium",
                        evidence=f"Unfilled quantity ratio {unfilled_ratio:.4f} exceeds threshold {self.max_unfilled_ratio} (orders frequently clipped by constraints)",
                    )
                )

        return failures
