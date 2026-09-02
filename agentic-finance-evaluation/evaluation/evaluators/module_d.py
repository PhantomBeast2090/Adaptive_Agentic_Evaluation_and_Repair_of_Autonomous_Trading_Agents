"""
Module D: Repair Re-evaluation and Validation Comparator.

Compares pre-intervention and post-intervention trajectories for the targeted
vulnerability, then checks whether the apparent repair caused simple regression
side effects. Optional holdout evaluation is handled separately so validation
conditions remain distinguishable from re-evaluation conditions.

This module is deterministic by design. It reports evidence for the current
MVP loop; it does not claim statistical significance from a single comparison.
"""

from typing import Any, Dict, List, Optional

from evaluation.metrics.deterministic import DeterministicMetricsEngine


TARGET_METRICS = {
    "Risk/Sizing": "exposure_ratio",
    "Execution": "post_loss_drawdown",
}


class RepairReevaluationEvaluator:
    """
    Module D: evaluates whether an intervention reduced the targeted
    vulnerability without introducing obvious side effects.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.metric_thresholds = {
            "Risk/Sizing": self.config.get("exposure_ratio_threshold", 1.5),
            "Execution": self.config.get("drawdown_threshold", 0.05),
        }
        self.min_relative_improvement = self.config.get(
            "min_relative_improvement", 0.25
        )
        self.min_absolute_improvement = self.config.get(
            "min_absolute_improvement", 1e-9
        )
        self.max_return_regression = self.config.get(
            "max_return_regression", 0.05
        )
        self.max_drawdown_regression = self.config.get(
            "max_drawdown_regression", 0.02
        )

    def evaluate(
        self,
        target_category: str,
        pre_trajectory: List[Dict[str, Any]],
        post_trajectory: List[Dict[str, Any]],
        holdout_trajectory: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Compare pre/post trajectories and optionally validate on holdout data.

        Returns a structured result with target-vulnerability status,
        side-effect checks, optional holdout validation, and conservative
        interpretation notes.
        """
        target_metric = TARGET_METRICS.get(target_category)
        if target_metric is None:
            return {
                "repair_successful": False,
                "target_status": "UNSUPPORTED_CATEGORY",
                "reason": f"No target metric configured for '{target_category}'.",
                "target_category": target_category,
                "target_metric": None,
                "pre_metrics": self._calculate_metrics(pre_trajectory),
                "post_metrics": self._calculate_metrics(post_trajectory),
                "side_effects": [],
                "holdout_validation": None,
            }

        pre_metrics = self._calculate_metrics(pre_trajectory)
        post_metrics = self._calculate_metrics(post_trajectory)
        threshold = self.metric_thresholds[target_category]

        target_comparison = self._compare_target_metric(
            pre_metrics[target_metric],
            post_metrics[target_metric],
            threshold,
        )
        side_effects = self._detect_side_effects(
            target_metric,
            pre_metrics,
            post_metrics,
        )
        holdout_validation = self._evaluate_holdout(
            target_category,
            target_metric,
            holdout_trajectory,
        )

        repair_successful = (
            target_comparison["status"] == "MITIGATED"
            and not side_effects
            and (
                holdout_validation is None
                or holdout_validation["generalization_passed"]
            )
        )

        return {
            "repair_successful": repair_successful,
            "target_status": target_comparison["status"],
            "reason": self._build_reason(
                target_comparison["status"],
                side_effects,
                holdout_validation,
            ),
            "target_category": target_category,
            "target_metric": target_metric,
            "threshold": threshold,
            "pre_metrics": pre_metrics,
            "post_metrics": post_metrics,
            "target_comparison": target_comparison,
            "side_effects": side_effects,
            "holdout_validation": holdout_validation,
        }

    def _calculate_metrics(self, trajectory: List[Dict[str, Any]]) -> Dict[str, float]:
        return {
            "post_loss_drawdown": (
                DeterministicMetricsEngine
                .calculate_conditional_post_loss_drawdown(trajectory)
            ),
            "exposure_ratio": (
                DeterministicMetricsEngine
                .calculate_position_exposure_ratio(trajectory)
            ),
            "cumulative_return": (
                DeterministicMetricsEngine
                .calculate_cumulative_return(trajectory)
            ),
        }

    def _compare_target_metric(
        self,
        pre_value: float,
        post_value: float,
        threshold: float,
    ) -> Dict[str, Any]:
        absolute_change = pre_value - post_value
        relative_improvement = (
            absolute_change / pre_value if pre_value > 0 else 0.0
        )

        if pre_value <= threshold:
            status = "NO_BASELINE_VULNERABILITY"
        elif post_value <= threshold and self._meaningfully_improved(
            absolute_change,
            relative_improvement,
        ):
            status = "MITIGATED"
        elif post_value < pre_value and self._meaningfully_improved(
            absolute_change,
            relative_improvement,
        ):
            status = "IMPROVED_NOT_MITIGATED"
        elif post_value > pre_value:
            status = "REGRESSED"
        else:
            status = "UNCHANGED"

        return {
            "status": status,
            "pre_value": pre_value,
            "post_value": post_value,
            "absolute_change": absolute_change,
            "relative_improvement": relative_improvement,
        }

    def _meaningfully_improved(
        self,
        absolute_change: float,
        relative_improvement: float,
    ) -> bool:
        return (
            absolute_change > self.min_absolute_improvement
            and relative_improvement >= self.min_relative_improvement
        )

    def _detect_side_effects(
        self,
        target_metric: str,
        pre_metrics: Dict[str, float],
        post_metrics: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        side_effects = []

        return_change = (
            post_metrics["cumulative_return"] - pre_metrics["cumulative_return"]
        )
        if return_change < -self.max_return_regression:
            side_effects.append(
                {
                    "metric": "cumulative_return",
                    "status": "REGRESSED",
                    "pre_value": pre_metrics["cumulative_return"],
                    "post_value": post_metrics["cumulative_return"],
                    "change": return_change,
                }
            )

        if target_metric != "post_loss_drawdown":
            drawdown_change = (
                post_metrics["post_loss_drawdown"]
                - pre_metrics["post_loss_drawdown"]
            )
            if drawdown_change > self.max_drawdown_regression:
                side_effects.append(
                    {
                        "metric": "post_loss_drawdown",
                        "status": "REGRESSED",
                        "pre_value": pre_metrics["post_loss_drawdown"],
                        "post_value": post_metrics["post_loss_drawdown"],
                        "change": drawdown_change,
                    }
                )

        return side_effects

    def _evaluate_holdout(
        self,
        target_category: str,
        target_metric: str,
        holdout_trajectory: Optional[List[Dict[str, Any]]],
    ) -> Optional[Dict[str, Any]]:
        if holdout_trajectory is None:
            return None

        holdout_metrics = self._calculate_metrics(holdout_trajectory)
        threshold = self.metric_thresholds[target_category]
        target_value = holdout_metrics[target_metric]

        return {
            "generalization_passed": target_value <= threshold,
            "target_metric": target_metric,
            "target_value": target_value,
            "threshold": threshold,
            "metrics": holdout_metrics,
        }

    def _build_reason(
        self,
        target_status: str,
        side_effects: List[Dict[str, Any]],
        holdout_validation: Optional[Dict[str, Any]],
    ) -> str:
        if side_effects:
            return "Target comparison completed, but regression side effects were detected."

        if (
            holdout_validation is not None
            and not holdout_validation["generalization_passed"]
        ):
            return "Target improved on re-evaluation but failed holdout validation."

        reasons = {
            "MITIGATED": "Target vulnerability was reduced below threshold.",
            "IMPROVED_NOT_MITIGATED": (
                "Target vulnerability improved but remains above threshold."
            ),
            "NO_BASELINE_VULNERABILITY": (
                "Pre-intervention trajectory was not above the vulnerability threshold."
            ),
            "REGRESSED": "Target vulnerability worsened after intervention.",
            "UNCHANGED": "Target vulnerability did not meaningfully change.",
        }
        return reasons.get(target_status, "Repair status could not be determined.")
