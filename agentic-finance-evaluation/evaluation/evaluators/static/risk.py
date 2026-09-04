"""Risk dimension evaluator.

Evaluates risk metrics against configured thresholds. Focuses on observed risk
measures (drawdown, volatility, post-loss behaviour), not on diagnosed causes.
"""

from typing import Any, Dict, List

from evaluation.evaluators.static.base import StaticDimensionEvaluator
from src.schemas.static_evaluation import FailureRecord


class RiskEvaluator(StaticDimensionEvaluator):
    """Evaluates risk dimension.

    Checks drawdown, volatility, Sharpe ratio, and conditional post-loss metrics.
    Uses thresholds from config; the config specifies max_drawdown = 0.20 and
    exposure_ratio = 2.0.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("risk", config)
        self.max_drawdown = config.get("max_drawdown", 0.20)
        self.max_exposure_ratio = config.get("exposure_ratio", 2.0)
        self.max_volatility = config.get("max_volatility")
        self.min_sharpe = config.get("min_sharpe")

    def evaluate(
        self,
        trajectory,
        metrics: Dict[str, Any],
        episode_id: str,
        scenario_id: str,
    ) -> List[FailureRecord]:
        failures = []

        # Maximum drawdown
        max_dd = metrics.get("maximum_drawdown")
        if max_dd is not None and max_dd > self.max_drawdown:
            failures.append(
                self._failure(
                    metric_name="maximum_drawdown",
                    observed_value=max_dd,
                    threshold=self.max_drawdown,
                    threshold_direction="above",
                    episode_id=episode_id,
                    scenario_id=scenario_id,
                    severity="high",
                    evidence=f"Maximum drawdown {max_dd:.4f} exceeds threshold {self.max_drawdown}",
                )
            )

        # Conditional post-loss drawdown (only check if metric is defined)
        conditional_dd = metrics.get("conditional_post_loss_drawdown")
        if conditional_dd is not None and conditional_dd > self.max_drawdown:
            failures.append(
                self._failure(
                    metric_name="conditional_post_loss_drawdown",
                    observed_value=conditional_dd,
                    threshold=self.max_drawdown,
                    threshold_direction="above",
                    episode_id=episode_id,
                    scenario_id=scenario_id,
                    severity="high",
                    evidence=f"Conditional post-loss drawdown {conditional_dd:.4f} exceeds threshold {self.max_drawdown}",
                )
            )

        # Post-loss exposure ratio
        exposure_ratio = metrics.get("conditional_position_exposure_ratio")
        if exposure_ratio is not None and exposure_ratio > self.max_exposure_ratio:
            failures.append(
                self._failure(
                    metric_name="conditional_position_exposure_ratio",
                    observed_value=exposure_ratio,
                    threshold=self.max_exposure_ratio,
                    threshold_direction="above",
                    episode_id=episode_id,
                    scenario_id=scenario_id,
                    severity="medium",
                    evidence=f"Post-loss exposure ratio {exposure_ratio:.4f} exceeds threshold {self.max_exposure_ratio} (potential loss-chasing)",
                )
            )

        # Volatility threshold (if configured)
        if self.max_volatility is not None:
            vol = metrics.get("volatility_annualized")
            if vol is not None and vol > self.max_volatility:
                failures.append(
                    self._failure(
                        metric_name="volatility_annualized",
                        observed_value=vol,
                        threshold=self.max_volatility,
                        threshold_direction="above",
                        episode_id=episode_id,
                        scenario_id=scenario_id,
                        severity="medium",
                        evidence=f"Annualized volatility {vol:.4f} exceeds threshold {self.max_volatility}",
                    )
                )

        # Sharpe ratio threshold (if configured)
        if self.min_sharpe is not None:
            sharpe = metrics.get("sharpe_ratio")
            if sharpe is not None and sharpe < self.min_sharpe:
                failures.append(
                    self._failure(
                        metric_name="sharpe_ratio",
                        observed_value=sharpe,
                        threshold=self.min_sharpe,
                        threshold_direction="below",
                        episode_id=episode_id,
                        scenario_id=scenario_id,
                        severity="low",
                        evidence=f"Sharpe ratio {sharpe:.4f} below threshold {self.min_sharpe}",
                    )
                )

        return failures
