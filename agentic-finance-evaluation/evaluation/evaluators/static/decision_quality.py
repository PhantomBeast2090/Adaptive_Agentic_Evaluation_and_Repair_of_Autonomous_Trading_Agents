"""Decision quality dimension evaluator.

IMPORTANT: Decision quality requires ground truth about optimal or correct actions.
No such ground truth exists in this repository. Historical market replay does not
provide a counterfactual: we observe what happened, not what would have happened
under alternative actions.

This evaluator explicitly marks the dimension as UNSUPPORTED rather than fabricating
ground truth or inventing oracle actions.
"""

from typing import Any, Dict, List

from evaluation.evaluators.static.base import StaticDimensionEvaluator
from src.schemas.static_evaluation import FailureRecord


class DecisionQualityEvaluator(StaticDimensionEvaluator):
    """Decision quality evaluator (UNSUPPORTED).

    Ground truth for decision quality does not exist in this environment:
    - No optimal action labels
    - No oracle trading decisions
    - No counterfactual market outcomes
    - Historical replay shows realized path only, not alternative paths

    This evaluator always returns an empty failure list because the dimension
    cannot be measured with the current data. It exists as a placeholder for
    future work that might add:
    - Synthetic scenarios with known optimal policies
    - Expert-labeled decision datasets
    - Simulation environments with ground truth

    DO NOT fabricate decision quality scores. The absence of this metric is
    scientifically preferable to fake evidence.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("decision_quality", config)

    def evaluate(
        self,
        trajectory,
        metrics: Dict[str, Any],
        episode_id: str,
        scenario_id: str,
    ) -> List[FailureRecord]:
        """Always returns empty list: decision quality is unsupported.

        No ground truth exists for optimal actions in historical market replay.
        """
        return []
