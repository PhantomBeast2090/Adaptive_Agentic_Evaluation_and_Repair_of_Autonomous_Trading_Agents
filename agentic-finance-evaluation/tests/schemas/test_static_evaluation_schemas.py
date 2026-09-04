"""Tests for static evaluation schemas."""

import json

import pytest

from src.schemas.static_evaluation import (
    EpisodeEvaluation,
    FailureRecord,
    StaticAgentProfile,
    StaticEvaluationResult,
)


def test_failure_record_creation():
    failure = FailureRecord(
        dimension="risk",
        metric_name="maximum_drawdown",
        observed_value=0.35,
        threshold=0.20,
        threshold_direction="above",
        episode_id="ep_001",
        scenario_id="scenario_001",
        severity="high",
        evidence="Maximum drawdown 0.35 exceeds threshold 0.20",
    )

    assert failure.dimension == "risk"
    assert failure.metric_name == "maximum_drawdown"
    assert failure.observed_value == 0.35
    assert failure.threshold == 0.20
    assert failure.severity == "high"
    assert failure.timestamp  # Should be set automatically


def test_failure_record_with_none_values():
    """Metrics can be undefined (None) and thresholds can be None for categorical failures."""
    failure = FailureRecord(
        dimension="constraint",
        metric_name="invalid_action_rate",
        observed_value=None,
        threshold=None,
        episode_id="ep_001",
        scenario_id="scenario_001",
        severity="critical",
        evidence="Malformed action submitted",
    )

    assert failure.observed_value is None
    assert failure.threshold is None


def test_failure_record_serialization():
    failure = FailureRecord(
        dimension="safety",
        metric_name="attempted_short_sale_count",
        observed_value=2.0,
        threshold=0.0,
        threshold_direction="above",
        episode_id="ep_001",
        scenario_id="scenario_001",
        severity="critical",
        evidence="2 attempted short sales",
    )

    # Should be JSON-serializable
    serialized = json.loads(json.dumps(failure.model_dump(), default=str))
    assert serialized["dimension"] == "safety"
    assert serialized["metric_name"] == "attempted_short_sale_count"


def test_episode_evaluation_creation():
    failures = [
        FailureRecord(
            dimension="risk",
            metric_name="maximum_drawdown",
            observed_value=0.25,
            threshold=0.20,
            threshold_direction="above",
            episode_id="ep_001",
            scenario_id="scenario_001",
            severity="high",
            evidence="Exceeded drawdown threshold",
        )
    ]

    ep_eval = EpisodeEvaluation(
        episode_id="ep_001",
        scenario_id="scenario_001",
        agent_id="test_agent",
        agent_version="v1.0",
        trajectory_digest="abc123",
        metrics={"total_return": 0.05, "maximum_drawdown": 0.25},
        failures=failures,
        dimensions_evaluated=["performance", "risk"],
        dimensions_passed=["performance"],
        dimensions_failed=["risk"],
    )

    assert ep_eval.episode_id == "ep_001"
    assert len(ep_eval.failures) == 1
    assert ep_eval.dimensions_passed == ["performance"]
    assert ep_eval.dimensions_failed == ["risk"]


def test_episode_evaluation_no_failures():
    ep_eval = EpisodeEvaluation(
        episode_id="ep_002",
        scenario_id="scenario_002",
        agent_id="test_agent",
        agent_version="v1.0",
        trajectory_digest="def456",
        metrics={"total_return": 0.10, "maximum_drawdown": 0.05},
        failures=[],
        dimensions_evaluated=["performance", "risk", "safety"],
        dimensions_passed=["performance", "risk", "safety"],
        dimensions_failed=[],
    )

    assert len(ep_eval.failures) == 0
    assert len(ep_eval.dimensions_passed) == 3
    assert len(ep_eval.dimensions_failed) == 0


def test_static_agent_profile_creation():
    profile = StaticAgentProfile(
        agent_id="test_agent",
        agent_version="v1.0",
        evaluation_run_id="run_001",
        episodes_evaluated=10,
        episodes_with_failures=3,
        total_failures=5,
        failures_by_dimension={"risk": 3, "safety": 2},
        failures_by_severity={"high": 3, "critical": 2},
        metric_distributions={
            "total_return": {"min": -0.05, "max": 0.15, "mean": 0.05, "median": 0.06, "p95": 0.12}
        },
        dimensions_evaluated=["performance", "risk", "safety"],
        scenario_ids=["s1", "s2", "s3"],
        holdout_used=False,
    )

    assert profile.agent_id == "test_agent"
    assert profile.episodes_evaluated == 10
    assert profile.total_failures == 5
    assert profile.holdout_used is False
    assert profile.failures_by_dimension["risk"] == 3


def test_static_agent_profile_holdout_must_be_false():
    """Phase 2 static baseline must never use holdout."""
    profile = StaticAgentProfile(
        agent_id="test_agent",
        agent_version="v1.0",
        evaluation_run_id="run_001",
        episodes_evaluated=5,
        episodes_with_failures=0,
        total_failures=0,
        failures_by_dimension={},
        failures_by_severity={},
        metric_distributions={},
        dimensions_evaluated=["performance"],
        scenario_ids=["s1"],
        holdout_used=False,
    )

    assert profile.holdout_used is False


def test_static_evaluation_result_creation():
    profile = StaticAgentProfile(
        agent_id="agent1",
        agent_version="v1.0",
        evaluation_run_id="run_001",
        episodes_evaluated=5,
        episodes_with_failures=1,
        total_failures=2,
        failures_by_dimension={"risk": 2},
        failures_by_severity={"high": 2},
        metric_distributions={},
        dimensions_evaluated=["performance", "risk"],
        scenario_ids=["s1", "s2"],
        holdout_used=False,
    )

    ep_eval = EpisodeEvaluation(
        episode_id="ep_001",
        scenario_id="s1",
        agent_id="agent1",
        agent_version="v1.0",
        trajectory_digest="abc",
        metrics={"total_return": 0.05},
        failures=[],
        dimensions_evaluated=["performance", "risk"],
        dimensions_passed=["performance", "risk"],
        dimensions_failed=[],
    )

    result = StaticEvaluationResult(
        run_id="run_001",
        experiment_id="exp_001",
        description="Test evaluation",
        agent_profiles=[profile],
        episode_evaluations=[ep_eval],
        scenario_ids=["s1", "s2"],
        scenario_source_splits=["discovery"],
        holdout_scenario_ids=["h1", "h2"],
        configuration={"test": "config"},
        total_episodes=5,
        total_failures=2,
        dimensions=["performance", "risk"],
        started_at="2026-09-04T00:00:00Z",
    )

    assert result.run_id == "run_001"
    assert len(result.agent_profiles) == 1
    assert len(result.episode_evaluations) == 1
    assert result.total_failures == 2
    assert "h1" in result.holdout_scenario_ids


def test_static_evaluation_result_to_dict():
    """Result must be serializable to dict for JSON output."""
    profile = StaticAgentProfile(
        agent_id="agent1",
        agent_version="v1.0",
        evaluation_run_id="run_001",
        episodes_evaluated=1,
        episodes_with_failures=0,
        total_failures=0,
        failures_by_dimension={},
        failures_by_severity={},
        metric_distributions={},
        dimensions_evaluated=["performance"],
        scenario_ids=["s1"],
        holdout_used=False,
    )

    result = StaticEvaluationResult(
        run_id="run_001",
        experiment_id="exp_001",
        description="Test",
        agent_profiles=[profile],
        episode_evaluations=[],
        scenario_ids=["s1"],
        scenario_source_splits=["discovery"],
        holdout_scenario_ids=[],
        configuration={},
        total_episodes=1,
        total_failures=0,
        dimensions=["performance"],
        started_at="2026-09-04T00:00:00Z",
    )

    result_dict = result.to_dict()
    assert isinstance(result_dict, dict)
    assert result_dict["run_id"] == "run_001"

    # Should be JSON-serializable
    json_str = json.dumps(result_dict, default=str)
    restored = json.loads(json_str)
    assert restored["run_id"] == "run_001"
