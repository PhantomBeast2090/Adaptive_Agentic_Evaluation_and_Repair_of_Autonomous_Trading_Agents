"""Performance dimension evaluator.

Evaluates financial performance metrics against absolute thresholds or relative
benchmarks. Does not invent optimal actions or oracle returns.
"""

from typing import Any, Dict, List

from evaluation.evaluators.static.base import StaticDimensionEvaluator
from src.schemas.static_evaluation import FailureRecord


class PerformanceEvaluator(StaticDimensionEvaluator):
    """Evaluates financial performance dimension.

    Checks metrics like total return, final value, and market-relative performance.
    Thresholds are configurable; there is no universal "good" return.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("performance", config)
        # Optional thresholds from config
        self.min_return = config.get("min_return")
        self.min_final_value = config.get("min_final_value")
        self.min_excess_return = config.get("min_excess_return")

    def evaluate(
        self,
        trajectory,
        metrics: Dict[str, Any],
        episode_id: str,
        scenario_id: str,
    ) -> List[FailureRecord]:
        failures = []

        # Total return threshold
        if self.min_return is not None:
            total_return = metrics.get("total_return")
            if total_return is not None and total_return < self.min_return:
                failures.append(
                    self._failure(
                        metric_name="total_return",
                        observed_value=total_return,
                        threshold=self.min_return,
                        threshold_direction="below",
                        episode_id=episode_id,
                        scenario_id=scenario_id,
                        severity="medium",
                        evidence=f"Total return {total_return:.4f} below threshold {self.min_return}",
                    )
                )

        # Final value threshold
        if self.min_final_value is not None:
            final_value = metrics.get("final_portfolio_value")
            if final_value is not None and final_value < self.min_final_value:
                failures.append(
                    self._failure(
                        metric_name="final_portfolio_value",
                        observed_value=final_value,
                        threshold=self.min_final_value,
                        threshold_direction="below",
                        episode_id=episode_id,
                        scenario_id=scenario_id,
                        severity="high",
                        evidence=f"Final portfolio value {final_value:.2f} below threshold {self.min_final_value}",
                    )
                )

        # Excess return vs market
        if self.min_excess_return is not None:
            excess = metrics.get("excess_return_vs_market")
            if excess is not None and excess < self.min_excess_return:
                failures.append(
                    self._failure(
                        metric_name="excess_return_vs_market",
                        observed_value=excess,
                        threshold=self.min_excess_return,
                        threshold_direction="below",
                        episode_id=episode_id,
                        scenario_id=scenario_id,
                        severity="low",
                        evidence=f"Excess return vs market {excess:.4f} below threshold {self.min_excess_return}",
                    )
                )

        return failures
