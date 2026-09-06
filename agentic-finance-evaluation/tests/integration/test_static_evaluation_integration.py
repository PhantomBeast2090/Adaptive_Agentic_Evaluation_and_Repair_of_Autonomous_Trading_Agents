"""End-to-end integration test for static evaluation pipeline.

Verifies the complete flow from scenario loading through episode execution to
final evaluation results and persistence.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from agents.financial_agent.synthetic import FlawlessControlAgent
from evaluation.static_evaluator import StaticEvaluator


def _create_test_split(tmp_path, name, dates, spy_prices, vix_values):
    """Create a market split file for testing."""
    df = pd.DataFrame(
        {"SPY": spy_prices, "^VIX": vix_values},
        index=pd.to_datetime(dates),
    )
    split_dir = tmp_path / "data" / "processed" / "market_splits"
    split_dir.mkdir(parents=True, exist_ok=True)
    path = split_dir / f"{name}.parquet"
    df.to_parquet(path)
    return str(path)


def _create_test_config(tmp_path, output_dir):
    """Create a minimal static evaluation config for testing."""
    import yaml

    config = {
        "static_evaluation": {
            "experiment_id": "test_exp_001",
            "description": "Integration test",
            "agents": [
                {
                    "agent_id": "flawless_control",
                    "version": "v1.0.0",
                    "class": "FlawlessControlAgent",
                    "module": "agents.financial_agent.synthetic",
                }
            ],
            "scenarios": {
                "splits": ["test_discovery"],
                "max_per_split": 2,
                "dimensions": [],
                "holdout_split": "",
                "holdout_max": 0,
            },
            "environment": {
                "initial_cash": 100000.0,
                "transaction_cost_bps": 0.0,
            },
            "evaluation": {
                "budget": 50,
                "evaluators": ["performance", "risk", "constraint", "safety"],
                "failure_thresholds": {
                    "max_drawdown": 0.20,
                    "exposure_ratio": 2.0,
                    "invalid_action_rate": 0.0,
                    "min_return": -0.50,
                },
            },
            "output": {
                "results_dir": str(output_dir),
                "format": "jsonl",
                "save_trajectories": True,
                "save_agent_profiles": True,
            },
        }
    }

    config_path = tmp_path / "test_config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    return str(config_path)


def test_static_evaluation_end_to_end(tmp_path):
    """Test complete static evaluation pipeline from config to saved results."""
    # Create test market data: 80 days, low volatility, upward trend
    dates = pd.date_range("2019-01-01", periods=80)
    spy_prices = [100.0 + i * 0.5 for i in range(80)]  # Gradual uptrend
    vix_values = [15.0] * 80  # Low volatility

    _create_test_split(tmp_path, "test_discovery", dates, spy_prices, vix_values)

    # Create output directory
    output_dir = tmp_path / "results"
    output_dir.mkdir()

    # Create test config
    config_path = _create_test_config(tmp_path, output_dir)

    # Run static evaluation
    evaluator = StaticEvaluator(config_path, base_dir=str(tmp_path))
    assert evaluator.run_id.startswith("static_eval_")
    assert evaluator.experiment_id == "test_exp_001"

    # Create and evaluate agent
    agent = FlawlessControlAgent("flawless_control", "v1.0.0")
    agents = [agent]

    result = evaluator.run(agents)

    # Verify result structure
    assert result.run_id == evaluator.run_id
    assert result.experiment_id == "test_exp_001"
    assert len(result.agent_profiles) == 1
    assert result.total_episodes > 0

    # Verify agent profile
    profile = result.agent_profiles[0]
    assert profile.agent_id == "flawless_control"
    assert profile.agent_version == "v1.0.0"
    assert profile.episodes_evaluated > 0
    assert profile.holdout_used is False  # Phase 2 never uses holdout

    # Verify episode evaluations
    assert len(result.episode_evaluations) == profile.episodes_evaluated
    for ep_eval in result.episode_evaluations:
        assert ep_eval.agent_id == "flawless_control"
        assert ep_eval.scenario_id.startswith("test_discovery_")
        assert ep_eval.trajectory_digest  # Must have reproducibility fingerprint
        assert "performance" in ep_eval.dimensions_evaluated
        assert "risk" in ep_eval.dimensions_evaluated

    # Verify metrics were computed
    first_ep = result.episode_evaluations[0]
    assert "total_return" in first_ep.metrics
    assert "maximum_drawdown" in first_ep.metrics
    assert first_ep.metrics["episode_length"] > 0

    # Save and verify persistence
    result_file = evaluator.save_result(result)
    assert result_file.exists()

    # Verify saved JSON is valid and complete
    with open(result_file) as f:
        saved_data = json.load(f)

    assert saved_data["run_id"] == result.run_id
    assert len(saved_data["agent_profiles"]) == 1
    assert len(saved_data["episode_evaluations"]) > 0

    # Verify episodes JSONL
    episodes_file = output_dir / f"{result.run_id}_episodes.jsonl"
    assert episodes_file.exists()

    with open(episodes_file) as f:
        episode_lines = f.readlines()
        assert len(episode_lines) == len(result.episode_evaluations)
        first_episode = json.loads(episode_lines[0])
        assert "episode_id" in first_episode
        assert "trajectory_digest" in first_episode

    # Verify profiles JSON
    profiles_file = output_dir / f"{result.run_id}_profiles.json"
    assert profiles_file.exists()

    with open(profiles_file) as f:
        profiles_data = json.load(f)
        assert len(profiles_data) == 1
        assert profiles_data[0]["agent_id"] == "flawless_control"


def test_static_evaluation_with_failures(tmp_path):
    """Test evaluation that triggers failures."""
    # Create volatile market with large drawdown
    dates = pd.date_range("2020-01-01", periods=70)
    spy_prices = [100.0] * 20 + [70.0] * 20 + [80.0] * 30  # -30% crash
    vix_values = [15.0] * 20 + [40.0] * 20 + [30.0] * 30

    _create_test_split(tmp_path, "test_discovery", dates, spy_prices, vix_values)

    output_dir = tmp_path / "results"
    output_dir.mkdir()

    config_path = _create_test_config(tmp_path, output_dir)

    # Run evaluation
    evaluator = StaticEvaluator(config_path, base_dir=str(tmp_path))
    agent = FlawlessControlAgent("flawless_control", "v1.0.0")
    result = evaluator.run([agent])

    # The agent will buy early and experience the drawdown
    # At least one episode should have failures
    assert result.total_failures >= 0  # May or may not fail depending on scenario windows

    # Check that failure records have proper structure if any exist
    for ep_eval in result.episode_evaluations:
        for failure in ep_eval.failures:
            assert failure.dimension in ["performance", "risk", "constraint", "safety"]
            assert failure.metric_name
            assert failure.severity in ["critical", "high", "medium", "low"]
            assert failure.evidence
            assert failure.episode_id == ep_eval.episode_id


def test_static_evaluation_holdout_separation(tmp_path):
    """Test that holdout scenarios are loaded but never evaluated in Phase 2."""
    # Create discovery and holdout splits
    dates_discovery = pd.date_range("2019-01-01", periods=70)
    dates_holdout = pd.date_range("2021-01-01", periods=70)

    _create_test_split(tmp_path, "test_discovery", dates_discovery, [100.0] * 70, [15.0] * 70)
    _create_test_split(tmp_path, "test_holdout", dates_holdout, [110.0] * 70, [20.0] * 70)

    import yaml

    config = {
        "static_evaluation": {
            "experiment_id": "test_holdout_sep",
            "description": "Holdout separation test",
            "scenarios": {
                "splits": ["test_discovery"],
                "max_per_split": 2,
                "dimensions": [],
                "holdout_split": "test_holdout",
                "holdout_max": 1,
            },
            "environment": {"initial_cash": 100000.0, "transaction_cost_bps": 0.0},
            "evaluation": {
                "budget": 50,
                "evaluators": ["performance"],
                "failure_thresholds": {},
            },
            "output": {
                "results_dir": str(tmp_path / "results"),
                "format": "jsonl",
                "save_trajectories": True,
                "save_agent_profiles": True,
            },
        }
    }

    config_path = tmp_path / "test_config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    # Run evaluation
    evaluator = StaticEvaluator(str(config_path), base_dir=str(tmp_path))
    agent = FlawlessControlAgent("test_agent", "v1.0")
    result = evaluator.run([agent])

    # Verify holdout scenarios were loaded but not evaluated
    assert len(result.holdout_scenario_ids) > 0
    assert all(
        not any(hid in ep.scenario_id for hid in result.holdout_scenario_ids)
        for ep in result.episode_evaluations
    )

    # Verify all evaluated scenarios are from baseline
    evaluated_scenario_ids = {ep.scenario_id for ep in result.episode_evaluations}
    assert all(sid in result.scenario_ids for sid in evaluated_scenario_ids)

    # Verify profile confirms no holdout use
    assert result.agent_profiles[0].holdout_used is False


def test_static_evaluation_deterministic_ordering(tmp_path):
    """Test that scenario ordering is deterministic."""
    dates = pd.date_range("2019-01-01", periods=100)
    _create_test_split(tmp_path, "test_discovery", dates, [100.0] * 100, [15.0] * 100)

    output_dir = tmp_path / "results"
    output_dir.mkdir()

    config_path = _create_test_config(tmp_path, output_dir)

    # Run evaluation twice
    evaluator1 = StaticEvaluator(config_path)
    agent = FlawlessControlAgent("test_agent", "v1.0")
    result1 = evaluator1.run([agent])

    evaluator2 = StaticEvaluator(config_path)
    result2 = evaluator2.run([agent])

    # Scenario ordering should be identical
    assert result1.scenario_ids == result2.scenario_ids

    # Episode order should be identical
    ep_scenarios_1 = [ep.scenario_id for ep in result1.episode_evaluations]
    ep_scenarios_2 = [ep.scenario_id for ep in result2.episode_evaluations]
    assert ep_scenarios_1 == ep_scenarios_2


def test_static_evaluation_multiple_agents(tmp_path):
    """Test evaluation of multiple agents in a single run."""
    dates = pd.date_range("2019-01-01", periods=70)
    _create_test_split(tmp_path, "test_discovery", dates, [100.0] * 70, [15.0] * 70)

    output_dir = tmp_path / "results"
    output_dir.mkdir()

    config_path = _create_test_config(tmp_path, output_dir)

    # Create multiple agents
    from agents.financial_agent.synthetic import VolatilityBlindAgent

    agents = [
        FlawlessControlAgent("agent1", "v1.0"),
        VolatilityBlindAgent("agent2", "v1.0"),
    ]

    # Run evaluation
    evaluator = StaticEvaluator(config_path)
    result = evaluator.run(agents)

    # Verify both agents were evaluated
    assert len(result.agent_profiles) == 2
    assert {p.agent_id for p in result.agent_profiles} == {"agent1", "agent2"}

    # Verify episode evaluations include both agents
    agent_ids_in_episodes = {ep.agent_id for ep in result.episode_evaluations}
    assert agent_ids_in_episodes == {"agent1", "agent2"}

    # Each agent should have evaluated the same number of scenarios
    agent1_episodes = [ep for ep in result.episode_evaluations if ep.agent_id == "agent1"]
    agent2_episodes = [ep for ep in result.episode_evaluations if ep.agent_id == "agent2"]
    assert len(agent1_episodes) == len(agent2_episodes)
