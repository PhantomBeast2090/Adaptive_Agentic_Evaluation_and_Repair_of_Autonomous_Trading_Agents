"""Tests for static dimension evaluators."""

import pytest

from evaluation.evaluators.static.performance import PerformanceEvaluator
from evaluation.evaluators.static.risk import RiskEvaluator
from evaluation.evaluators.static.constraint import ConstraintEvaluator
from evaluation.evaluators.static.safety import SafetyEvaluator
from evaluation.evaluators.static.consistency import ConsistencyEvaluator
from evaluation.evaluators.static.decision_quality import DecisionQualityEvaluator


class MockTrajectory:
    """Minimal mock trajectory for testing evaluators."""

    def __init__(self):
        self.steps = []


# --------------------------------------------------------------------------- #
# Performance Evaluator Tests
# --------------------------------------------------------------------------- #


def test_performance_evaluator_no_failures():
    config = {"min_return": -0.10, "min_final_value": 95000.0}
    evaluator = PerformanceEvaluator(config)

    metrics = {"total_return": 0.05, "final_portfolio_value": 105000.0}
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")

    assert len(failures) == 0


def test_performance_evaluator_return_below_threshold():
    config = {"min_return": 0.0}
    evaluator = PerformanceEvaluator(config)

    metrics = {"total_return": -0.05}
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")

    assert len(failures) == 1
    assert failures[0].dimension == "performance"
    assert failures[0].metric_name == "total_return"
    assert failures[0].observed_value == -0.05
    assert failures[0].threshold == 0.0
    assert failures[0].threshold_direction == "below"


def test_performance_evaluator_final_value_below_threshold():
    config = {"min_final_value": 100000.0}
    evaluator = PerformanceEvaluator(config)

    metrics = {"final_portfolio_value": 90000.0}
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")

    assert len(failures) == 1
    assert failures[0].metric_name == "final_portfolio_value"
    assert failures[0].severity == "high"


def test_performance_evaluator_multiple_failures():
    config = {"min_return": 0.05, "min_excess_return": 0.01}
    evaluator = PerformanceEvaluator(config)

    metrics = {"total_return": 0.02, "excess_return_vs_market": -0.01}
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")

    assert len(failures) == 2
    assert {f.metric_name for f in failures} == {"total_return", "excess_return_vs_market"}


def test_performance_evaluator_undefined_metric_no_failure():
    """None metrics should not trigger failures."""
    config = {"min_return": 0.0}
    evaluator = PerformanceEvaluator(config)

    metrics = {"total_return": None}  # Undefined
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")

    assert len(failures) == 0


# --------------------------------------------------------------------------- #
# Risk Evaluator Tests
# --------------------------------------------------------------------------- #


def test_risk_evaluator_no_failures():
    config = {"max_drawdown": 0.20, "exposure_ratio": 2.0}
    evaluator = RiskEvaluator(config)

    metrics = {
        "maximum_drawdown": 0.10,
        "conditional_post_loss_drawdown": 0.12,
        "conditional_position_exposure_ratio": 1.2,
    }
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")

    assert len(failures) == 0


def test_risk_evaluator_drawdown_exceeds_threshold():
    config = {"max_drawdown": 0.20}
    evaluator = RiskEvaluator(config)

    metrics = {"maximum_drawdown": 0.35}
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")

    assert len(failures) == 1
    assert failures[0].metric_name == "maximum_drawdown"
    assert failures[0].observed_value == 0.35
    assert failures[0].threshold == 0.20
    assert failures[0].threshold_direction == "above"
    assert failures[0].severity == "high"


def test_risk_evaluator_exposure_ratio_exceeds_threshold():
    config = {"exposure_ratio": 2.0}
    evaluator = RiskEvaluator(config)

    metrics = {"conditional_position_exposure_ratio": 2.5}
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")

    assert len(failures) == 1
    assert failures[0].metric_name == "conditional_position_exposure_ratio"
    assert "loss-chasing" in failures[0].evidence


def test_risk_evaluator_conditional_drawdown_when_defined():
    """Conditional metrics should only fail when they are defined (not None)."""
    config = {"max_drawdown": 0.20}
    evaluator = RiskEvaluator(config)

    # Conditional metric is None (no losing step occurred)
    metrics = {"conditional_post_loss_drawdown": None}
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")
    assert len(failures) == 0

    # Conditional metric is defined and exceeds threshold
    metrics = {"conditional_post_loss_drawdown": 0.30}
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")
    assert len(failures) == 1


# --------------------------------------------------------------------------- #
# Constraint Evaluator Tests
# --------------------------------------------------------------------------- #


def test_constraint_evaluator_no_failures():
    config = {"invalid_action_rate": 0.0}
    evaluator = ConstraintEvaluator(config)

    metrics = {"invalid_action_rate": 0.0, "malformed_action_count": 0}
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")

    assert len(failures) == 0


def test_constraint_evaluator_invalid_action_rate_above_threshold():
    config = {"invalid_action_rate": 0.0}
    evaluator = ConstraintEvaluator(config)

    metrics = {"invalid_action_rate": 0.1, "malformed_action_count": 3}
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")

    assert len(failures) == 1
    assert failures[0].metric_name == "invalid_action_rate"
    assert failures[0].severity == "critical"
    assert "3 malformed submissions" in failures[0].evidence


def test_constraint_evaluator_unfilled_ratio_threshold():
    config = {"max_unfilled_ratio": 0.10}
    evaluator = ConstraintEvaluator(config)

    metrics = {"unfilled_quantity_ratio": 0.25}
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")

    assert len(failures) == 1
    assert failures[0].metric_name == "unfilled_quantity_ratio"


# --------------------------------------------------------------------------- #
# Safety Evaluator Tests
# --------------------------------------------------------------------------- #


def test_safety_evaluator_no_failures():
    evaluator = SafetyEvaluator({})

    metrics = {"attempted_short_sale_count": 0, "attempted_leverage_count": 0}
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")

    assert len(failures) == 0


def test_safety_evaluator_attempted_short_sale():
    evaluator = SafetyEvaluator({})

    metrics = {"attempted_short_sale_count": 2, "attempted_leverage_count": 0}
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")

    assert len(failures) == 1
    assert failures[0].metric_name == "attempted_short_sale_count"
    assert failures[0].observed_value == 2
    assert failures[0].threshold == 0
    assert failures[0].severity == "critical"
    assert "short sale" in failures[0].evidence.lower()


def test_safety_evaluator_attempted_leverage():
    evaluator = SafetyEvaluator({})

    metrics = {"attempted_short_sale_count": 0, "attempted_leverage_count": 1}
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")

    assert len(failures) == 1
    assert failures[0].metric_name == "attempted_leverage_count"
    assert failures[0].severity == "critical"


def test_safety_evaluator_multiple_violations():
    evaluator = SafetyEvaluator({})

    metrics = {"attempted_short_sale_count": 3, "attempted_leverage_count": 2}
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")

    assert len(failures) == 2
    assert {f.metric_name for f in failures} == {
        "attempted_short_sale_count",
        "attempted_leverage_count",
    }


# --------------------------------------------------------------------------- #
# Consistency Evaluator Tests
# --------------------------------------------------------------------------- #


def test_consistency_evaluator_no_failures():
    config = {}
    evaluator = ConsistencyEvaluator(config)

    metrics = {"action_repeatability": None}  # Typically undefined
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")

    assert len(failures) == 0


def test_consistency_evaluator_repeatability_below_threshold():
    config = {"min_action_repeatability": 0.90}
    evaluator = ConsistencyEvaluator(config)

    metrics = {"action_repeatability": 0.60}
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")

    assert len(failures) == 1
    assert failures[0].metric_name == "action_repeatability"
    assert failures[0].observed_value == 0.60
    assert failures[0].threshold == 0.90


def test_consistency_evaluator_undefined_metric_no_failure():
    """action_repeatability is typically None (no repeated observations)."""
    config = {"min_action_repeatability": 0.90}
    evaluator = ConsistencyEvaluator(config)

    metrics = {"action_repeatability": None}
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")

    assert len(failures) == 0


# --------------------------------------------------------------------------- #
# Decision Quality Evaluator Tests
# --------------------------------------------------------------------------- #


def test_decision_quality_always_unsupported():
    """Decision quality has no ground truth and always returns empty."""
    evaluator = DecisionQualityEvaluator({})

    metrics = {"any_metric": 0.5}
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")

    assert len(failures) == 0


def test_decision_quality_dimension_name():
    evaluator = DecisionQualityEvaluator({})
    assert evaluator.dimension == "decision_quality"


# --------------------------------------------------------------------------- #
# Edge Cases and Invalid Inputs
# --------------------------------------------------------------------------- #


def test_evaluator_handles_empty_metrics():
    """Evaluators should handle empty metrics dict without crashing."""
    evaluator = PerformanceEvaluator({"min_return": 0.0})
    failures = evaluator.evaluate(MockTrajectory(), {}, "ep_001", "s_001")
    assert len(failures) == 0


def test_evaluator_handles_missing_threshold_config():
    """If threshold not in config, that check should be skipped."""
    evaluator = PerformanceEvaluator({})  # No thresholds configured

    metrics = {"total_return": -0.50, "final_portfolio_value": 50000.0}
    failures = evaluator.evaluate(MockTrajectory(), metrics, "ep_001", "s_001")

    assert len(failures) == 0  # No thresholds to violate
