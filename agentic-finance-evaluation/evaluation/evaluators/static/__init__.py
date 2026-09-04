"""Static evaluator registry and factory."""

from typing import Dict, Any, List

from evaluation.evaluators.static.base import StaticDimensionEvaluator
from evaluation.evaluators.static.performance import PerformanceEvaluator
from evaluation.evaluators.static.risk import RiskEvaluator
from evaluation.evaluators.static.constraint import ConstraintEvaluator
from evaluation.evaluators.static.safety import SafetyEvaluator
from evaluation.evaluators.static.consistency import ConsistencyEvaluator
from evaluation.evaluators.static.robustness import RobustnessEvaluator
from evaluation.evaluators.static.decision_quality import DecisionQualityEvaluator


EVALUATOR_REGISTRY = {
    "performance": PerformanceEvaluator,
    "risk": RiskEvaluator,
    "constraint": ConstraintEvaluator,
    "safety": SafetyEvaluator,
    "consistency": ConsistencyEvaluator,
    "robustness": RobustnessEvaluator,
    "decision_quality": DecisionQualityEvaluator,
}


def create_evaluators(config: Dict[str, Any]) -> Dict[str, StaticDimensionEvaluator]:
    """Create dimension evaluators from configuration.

    Args:
        config: Evaluation configuration containing dimension list and thresholds

    Returns:
        Dictionary mapping dimension name to evaluator instance
    """
    dimensions = config.get("evaluators", [])
    failure_thresholds = config.get("failure_thresholds", {})

    evaluators = {}
    for dimension in dimensions:
        if dimension not in EVALUATOR_REGISTRY:
            raise ValueError(f"Unknown dimension: {dimension}. Available: {list(EVALUATOR_REGISTRY.keys())}")

        evaluator_class = EVALUATOR_REGISTRY[dimension]
        evaluators[dimension] = evaluator_class(failure_thresholds)

    return evaluators
