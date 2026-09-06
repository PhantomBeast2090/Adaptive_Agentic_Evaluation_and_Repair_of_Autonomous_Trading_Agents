"""End-to-end integration test for static evaluation pipeline.

This test verifies the complete Phase 2 static evaluation pipeline:
    Scenario Loading → Episode Runner → Metrics → Evaluators → Result

It does NOT test adaptive scenario selection or diagnosis (those are Phase 3+).
It does NOT use holdout data for scoring (holdout is loaded but never evaluated).
"""

import json
import tempfile
from pathlib import Path

import pytest

from agents.financial_agent.synthetic import FlawlessControlAgent, LossChasingAgent
from environment.core import FinancialEnvironment
from evaluation.episode_runner import run_episode
from evaluation.evaluators.static import create_evaluators
from evaluation.metrics import static_metrics
from evaluation.static_evaluator import StaticEvaluator
from src.data.scenario_loader import ScenarioLoader
from src.schemas.static_evaluation import (
    EpisodeEvaluation,
    StaticAgentProfile,
    StaticEvaluationResult,
)


class TestStaticEvaluationPipeline:
    """Test the complete static evaluation pipeline."""

    def test_static_evaluator_instantiation(self):
        """Test that StaticEvaluator can be instantiated with config."""
        evaluator = StaticEvaluator()
        assert evaluator.run_id is not None
        assert evaluator.config is not None
        assert evaluator.baseline_scenarios is not None
        assert len(evaluator.baseline_scenarios) > 0
        # Holdout should be loaded but separate
        assert hasattr(evaluator, "holdout_scenarios")

    def test_scenario_loading(self):
        """Test that scenario loader works correctly."""
        loader = ScenarioLoader()
        scenarios = loader.load_scenarios()
        assert len(scenarios) > 0
        
        # Check that scenarios have required fields
        for scenario in scenarios:
            assert scenario.scenario_id is not None
            assert scenario.market_data_path is not None
            assert scenario.initial_cash > 0
            assert hasattr(scenario, "holdout")

    def test_single_episode_evaluation(self):
        """Test a single episode can be evaluated end-to-end."""
        # Create a simple scenario
        loader = ScenarioLoader()
        scenarios = loader.load_scenarios()
        scenario = scenarios[0]
        
        # Create environment
        env = FinancialEnvironment(
            data_path=scenario.market_data_path,
            initial_cash=scenario.initial_cash,
            transaction_cost_bps=scenario.transaction_cost_bps,
            start_date=scenario.start_date,
            end_date=scenario.end_date,
        )
        
        # Create agent
        agent = FlawlessControlAgent(agent_id="test_flawless", version="v1.0.0")
        
        # Run episode
        episode_id = f"test_episode_{agent.agent_id}_{scenario.scenario_id}"
        trajectory = run_episode(
            agent=agent,
            environment=env,
            scenario_id=scenario.scenario_id,
            episode_id=episode_id,
            seed=42,
        )
        
        # Verify trajectory is valid
        assert trajectory is not None
        assert len(trajectory.steps) > 0
        assert trajectory.episode_id == episode_id

    def test_metrics_computation(self):
        """Test that metrics can be computed from a trajectory."""
        # Create a simple scenario and run an episode
        loader = ScenarioLoader()
        scenarios = loader.load_scenarios()
        scenario = scenarios[0]
        
        env = FinancialEnvironment(
            data_path=scenario.market_data_path,
            initial_cash=scenario.initial_cash,
            transaction_cost_bps=scenario.transaction_cost_bps,
            start_date=scenario.start_date,
            end_date=scenario.end_date,
        )
        
        agent = FlawlessControlAgent(agent_id="test_metrics", version="v1.0.0")
        trajectory = run_episode(
            agent=agent,
            environment=env,
            scenario_id=scenario.scenario_id,
            episode_id="test_metrics",
            seed=42,
        )
        
        # Compute metrics
        metrics = static_metrics.compute_episode_metrics(trajectory)
        
        # Verify metrics are computed
        assert metrics is not None
        assert isinstance(metrics, dict)
        assert len(metrics) > 0
        
        # Check for key metrics
        assert "total_return" in metrics
        assert "maximum_drawdown" in metrics
        assert "final_portfolio_value" in metrics

    def test_evaluator_instantiation(self):
        """Test that dimension evaluators can be instantiated."""
        config = {
            "evaluators": ["performance", "risk", "constraint", "safety", "consistency"],
            "failure_thresholds": {
                "max_drawdown": 0.30,
                "exposure_ratio": 3.0,
                "min_return": -0.10,
            }
        }
        
        evaluators = create_evaluators(config)
        assert evaluators is not None
        assert len(evaluators) > 0
        
        # Check for expected dimensions
        expected_dimensions = ["performance", "risk", "constraint", "safety", "consistency"]
        for dim in expected_dimensions:
            assert dim in evaluators

    def test_dimension_evaluation(self):
        """Test that a dimension evaluator can evaluate an episode."""
        # Setup: create trajectory and metrics
        loader = ScenarioLoader()
        scenarios = loader.load_scenarios()
        scenario = scenarios[0]
        
        env = FinancialEnvironment(
            data_path=scenario.market_data_path,
            initial_cash=scenario.initial_cash,
            transaction_cost_bps=scenario.transaction_cost_bps,
            start_date=scenario.start_date,
            end_date=scenario.end_date,
        )
        
        agent = LossChasingAgent(agent_id="test_eval", version="v1.0.0")
        trajectory = run_episode(
            agent=agent,
            environment=env,
            scenario_id=scenario.scenario_id,
            episode_id="test_evaluation",
            seed=42,
        )
        
        metrics = static_metrics.compute_episode_metrics(trajectory)
        
        # Create evaluators
        config = {
            "evaluators": ["performance", "risk", "constraint", "safety", "consistency"],
            "failure_thresholds": {
                "max_drawdown": 0.15,
                "exposure_ratio": 2.0,
                "min_return": 0.0,
            }
        }
        evaluators = create_evaluators(config)
        
        # Evaluate on all dimensions
        all_failures = []
        for dimension, evaluator in evaluators.items():
            failures = evaluator.evaluate(
                trajectory=trajectory,
                metrics=metrics,
                episode_id="test_evaluation",
                scenario_id=scenario.scenario_id,
            )
            all_failures.extend(failures)
        
        # Verify result structure
        assert isinstance(all_failures, list)
        # Loss chasing agent may have failures; at minimum the structure is valid
        for failure in all_failures:
            assert failure.dimension is not None
            assert failure.metric_name is not None
            assert failure.episode_id == "test_evaluation"
            assert failure.scenario_id == scenario.scenario_id

    def test_agent_profile_creation(self):
        """Test that an agent profile can be created from episode evaluations."""
        evaluator = StaticEvaluator()
        agent = FlawlessControlAgent(agent_id="profile_test", version="v1.0.0")
        
        # Run evaluation for the agent
        profile = evaluator.evaluate_agent(agent)
        
        # Verify profile structure
        assert isinstance(profile, StaticAgentProfile)
        assert profile.agent_id == agent.agent_id
        assert profile.episodes_evaluated > 0
        assert profile.dimensions_evaluated is not None
        assert len(profile.dimensions_evaluated) > 0
        assert profile.holdout_used is False  # Phase 2 never uses holdout

    def test_static_evaluation_result_creation(self):
        """Test that a complete StaticEvaluationResult can be created."""
        evaluator = StaticEvaluator()
        agents = [
            FlawlessControlAgent(agent_id="result_test_1", version="v1.0.0"),
            LossChasingAgent(agent_id="result_test_2", version="v1.0.0"),
        ]
        
        # Run complete evaluation
        result = evaluator.run(agents)
        
        # Verify result structure
        assert isinstance(result, StaticEvaluationResult)
        assert result.run_id is not None
        assert result.agent_profiles is not None
        assert len(result.agent_profiles) == len(agents)
        assert result.episode_evaluations is not None
        assert result.total_episodes > 0
        assert result.dimensions is not None
        
        # Verify holdout is loaded but not used
        assert result.holdout_scenario_ids is not None
        # Holdout should never appear in scenario_ids (only in holdout_scenario_ids)
        for scenario_id in result.scenario_ids:
            assert scenario_id not in result.holdout_scenario_ids

    def test_static_evaluation_result_serialization(self):
        """Test that StaticEvaluationResult can be serialized to JSON."""
        evaluator = StaticEvaluator()
        agents = [FlawlessControlAgent(agent_id="serial_test", version="v1.0.0")]
        result = evaluator.run(agents)
        
        # Serialize to dict
        result_dict = result.to_dict()
        
        # Verify serialization
        assert isinstance(result_dict, dict)
        assert "run_id" in result_dict
        assert "agent_profiles" in result_dict
        assert "episode_evaluations" in result_dict
        
        # Verify JSON serializable
        json_str = json.dumps(result_dict, default=str)
        assert json_str is not None
        assert len(json_str) > 0

    def test_static_evaluation_result_persistence(self):
        """Test that evaluation results can be saved to disk."""
        evaluator = StaticEvaluator()
        agents = [FlawlessControlAgent(agent_id="persist_test", version="v1.0.0")]
        result = evaluator.run(agents)
        
        # Save to temporary directory
        with tempfile.TemporaryDirectory() as tmpdir:
            result_file = evaluator.save_result(result, tmpdir)
            
            # Verify file exists
            assert result_file.exists()
            
            # Verify file contains valid JSON
            with open(result_file, "r") as f:
                loaded = json.load(f)
                assert loaded["run_id"] == result.run_id
                assert len(loaded["agent_profiles"]) == len(agents)

    def test_reproducibility_with_seed(self):
        """Test that evaluation is reproducible with the same seed."""
        # Run evaluation 1
        loader1 = ScenarioLoader()
        scenarios1 = loader1.load_scenarios()
        scenario1 = scenarios1[0]
        
        env1 = FinancialEnvironment(
            data_path=scenario1.market_data_path,
            initial_cash=scenario1.initial_cash,
            transaction_cost_bps=scenario1.transaction_cost_bps,
            start_date=scenario1.start_date,
            end_date=scenario1.end_date,
        )
        
        agent1 = FlawlessControlAgent(agent_id="repro_1", version="v1.0.0")
        traj1 = run_episode(
            agent=agent1,
            environment=env1,
            scenario_id=scenario1.scenario_id,
            episode_id="repro_test_1",
            seed=42,
        )
        
        # Run evaluation 2 with same seed
        loader2 = ScenarioLoader()
        scenarios2 = loader2.load_scenarios()
        scenario2 = scenarios2[0]
        
        env2 = FinancialEnvironment(
            data_path=scenario2.market_data_path,
            initial_cash=scenario2.initial_cash,
            transaction_cost_bps=scenario2.transaction_cost_bps,
            start_date=scenario2.start_date,
            end_date=scenario2.end_date,
        )
        
        agent2 = FlawlessControlAgent(agent_id="repro_2", version="v1.0.0")
        traj2 = run_episode(
            agent=agent2,
            environment=env2,
            scenario_id=scenario2.scenario_id,
            episode_id="repro_test_2",
            seed=42,
        )
        
        # Verify determinism
        metrics1 = static_metrics.compute_episode_metrics(traj1)
        metrics2 = static_metrics.compute_episode_metrics(traj2)
        
        # Key metrics should match
        assert metrics1["total_return"] == metrics2["total_return"]
        assert metrics1["final_portfolio_value"] == metrics2["final_portfolio_value"]

    def test_no_holdout_leakage(self):
        """Test that holdout scenarios are never used in baseline evaluation."""
        evaluator = StaticEvaluator()
        
        # Verify baseline scenarios never include holdout
        for baseline_scenario in evaluator.baseline_scenarios:
            assert baseline_scenario.holdout is False
        
        # Verify holdout scenarios are excluded from baseline
        for holdout_scenario in evaluator.holdout_scenarios:
            assert holdout_scenario.holdout is True
            assert holdout_scenario not in evaluator.baseline_scenarios


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
