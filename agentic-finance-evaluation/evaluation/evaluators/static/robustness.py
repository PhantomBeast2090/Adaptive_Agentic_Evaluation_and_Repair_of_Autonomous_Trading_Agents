"""Robustness dimension evaluator.

Robustness is a cross-scenario property: it measures whether an agent's behaviour
degrades across different market conditions. A single trajectory cannot be labeled
"robust"; robustness requires aggregation across the fixed scenario set.

This evaluator does NOT operate on individual episodes. It is invoked at the
profile aggregation level.
"""

from typing import Any, Dict, List

from evaluation.evaluators.static.base import StaticDimensionEvaluator
from src.schemas.static_evaluation import FailureRecord


class RobustnessEvaluator(StaticDimensionEvaluator):
    """Evaluates robustness dimension (cross-scenario only).

    Robustness is measured by failure rate variance across scenarios, metric
    stability, and regime-specific performance. This evaluator returns an empty
    list for single-episode evaluation; it only produces failures at the
    profile aggregation level.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("robustness", config)
        self.max_failure_rate_variance = config.get("max_failure_rate_variance")
        self.min_scenarios_evaluated = config.get("min_scenarios_for_robustness", 3)

    def evaluate(
        self,
        trajectory,
        metrics: Dict[str, Any],
        episode_id: str,
        scenario_id: str,
    ) -> List[FailureRecord]:
        """Single-episode evaluation always returns empty for robustness.

        Robustness is a cross-scenario property and cannot be assessed from one
        trajectory. See evaluate_profile() for the actual robustness check.
        """
        return []

    def evaluate_profile(
        self,
        episode_evaluations: List[Any],  # List[EpisodeEvaluation]
        agent_id: str,
        agent_version: str,
    ) -> List[FailureRecord]:
        """Evaluate robustness across all episodes for this agent.

        This is called at the profile aggregation level, not per-episode.
        """
        failures = []

        if len(episode_evaluations) < self.min_scenarios_evaluated:
            # Not enough data to assess robustness
            return failures

        # Calculate failure rate per scenario
        scenario_failure_rates = {}
        for ep_eval in episode_evaluations:
            scenario_id = ep_eval.scenario_id
            had_failure = len(ep_eval.failures) > 0
            if scenario_id not in scenario_failure_rates:
                scenario_failure_rates[scenario_id] = []
            scenario_failure_rates[scenario_id].append(1.0 if had_failure else 0.0)

        # Compute variance in failure rates across scenarios
        if len(scenario_failure_rates) >= 2:
            import statistics

            scenario_means = [statistics.fmean(rates) for rates in scenario_failure_rates.values()]
            if len(scenario_means) >= 2:
                variance = statistics.variance(scenario_means)

                if self.max_failure_rate_variance is not None and variance > self.max_failure_rate_variance:
                    failures.append(
                        FailureRecord(
                            dimension=self.dimension,
                            metric_name="failure_rate_variance_across_scenarios",
                            observed_value=variance,
                            threshold=self.max_failure_rate_variance,
                            threshold_direction="above",
                            episode_id="",  # Profile-level, not episode-specific
                            scenario_id="",
                            severity="medium",
                            evidence=f"Failure rate variance {variance:.4f} across scenarios exceeds threshold {self.max_failure_rate_variance} (inconsistent performance across market conditions)",
                        )
                    )

        return failures
