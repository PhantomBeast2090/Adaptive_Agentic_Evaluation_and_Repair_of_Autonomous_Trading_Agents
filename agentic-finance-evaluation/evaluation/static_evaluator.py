"""Static evaluation orchestrator.

Executes the complete static evaluation pipeline:
    Fixed scenario set → Episode runner → Metrics → Evaluators → Agent profiles → Result

This is Phase 2: deterministic baseline evaluation with no adaptive behaviour,
diagnosis, or intervention. Holdout scenarios are loaded but never used for
scoring or adaptation.
"""

import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from agents.financial_agent.base import BaseTradingAgent
from environment.core import FinancialEnvironment
from evaluation.episode_runner import run_episode
from evaluation.evaluators.static import create_evaluators
from evaluation.evaluators.static.robustness import RobustnessEvaluator
from evaluation.metrics import static_metrics
from src.data.scenario_loader import ScenarioLoader
from src.schemas.static_evaluation import (
    EpisodeEvaluation,
    FailureRecord,
    StaticAgentProfile,
    StaticEvaluationResult,
)


class StaticEvaluator:
    """Orchestrates static evaluation across a fixed scenario set.

    Enforces:
    - Fixed scenario ordering (deterministic)
    - No adaptive scenario selection
    - No holdout use for baseline scoring
    - Reproducible evaluation
    """

    def __init__(self, config_path: str = "configs/static_evaluation.yaml"):
        import yaml

        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)["static_evaluation"]

        self.run_id = f"static_eval_{uuid4().hex[:8]}"
        self.experiment_id = self.config["experiment_id"]
        self.description = self.config["description"]

        # Load fixed scenario set
        self.loader = ScenarioLoader(config_path)
        self.scenarios = self.loader.load_scenarios()

        # Separate baseline and holdout
        self.baseline_scenarios = [s for s in self.scenarios if not s.holdout]
        self.holdout_scenarios = [s for s in self.scenarios if s.holdout]

        # Create dimension evaluators
        self.evaluators = create_evaluators(self.config["evaluation"])

        self.episode_evaluations: List[EpisodeEvaluation] = []
        self.started_at = datetime.now(timezone.utc).isoformat()

    def evaluate_agent(self, agent: BaseTradingAgent) -> StaticAgentProfile:
        """Evaluate one agent across the fixed baseline scenario set.

        Args:
            agent: The agent to evaluate

        Returns:
            StaticAgentProfile aggregating results across all baseline scenarios

        Note: Holdout scenarios are never evaluated in Phase 2 static baseline.
        """
        agent_episodes: List[EpisodeEvaluation] = []

        for scenario in self.baseline_scenarios:
            # Create environment for this scenario
            env = FinancialEnvironment(
                data_path=scenario.market_data_path,
                initial_cash=scenario.initial_cash,
                transaction_cost_bps=scenario.transaction_cost_bps,
                start_date=scenario.start_date,
                end_date=scenario.end_date,
            )

            # Run episode
            episode_id = f"{self.run_id}_{agent.agent_id}_{scenario.scenario_id}"
            trajectory = run_episode(
                agent=agent,
                environment=env,
                scenario_id=scenario.scenario_id,
                episode_id=episode_id,
                seed=None,  # Phase 2 agents are deterministic
            )

            # Compute metrics
            metrics = static_metrics.compute_episode_metrics(trajectory)

            # Evaluate across all dimensions
            all_failures: List[FailureRecord] = []
            dimensions_evaluated = []
            dimensions_passed = []
            dimensions_failed = []

            for dimension, evaluator in self.evaluators.items():
                dimensions_evaluated.append(dimension)
                failures = evaluator.evaluate(
                    trajectory=trajectory,
                    metrics=metrics,
                    episode_id=episode_id,
                    scenario_id=scenario.scenario_id,
                )
                if failures:
                    all_failures.extend(failures)
                    dimensions_failed.append(dimension)
                else:
                    dimensions_passed.append(dimension)

            # Create episode evaluation
            ep_eval = EpisodeEvaluation(
                episode_id=episode_id,
                scenario_id=scenario.scenario_id,
                agent_id=agent.agent_id,
                agent_version=agent.version,
                trajectory_digest=trajectory.content_digest(),
                metrics=metrics,
                failures=all_failures,
                dimensions_evaluated=dimensions_evaluated,
                dimensions_passed=dimensions_passed,
                dimensions_failed=dimensions_failed,
            )

            agent_episodes.append(ep_eval)
            self.episode_evaluations.append(ep_eval)

        # Aggregate into agent profile
        profile = self._create_agent_profile(agent, agent_episodes)
        return profile

    def _create_agent_profile(
        self, agent: BaseTradingAgent, episodes: List[EpisodeEvaluation]
    ) -> StaticAgentProfile:
        """Aggregate episode evaluations into an agent profile."""
        total_failures = sum(len(ep.failures) for ep in episodes)
        episodes_with_failures = sum(1 for ep in episodes if ep.failures)

        # Count failures by dimension
        failures_by_dimension: Dict[str, int] = {}
        for ep in episodes:
            for failure in ep.failures:
                failures_by_dimension[failure.dimension] = (
                    failures_by_dimension.get(failure.dimension, 0) + 1
                )

        # Count failures by severity
        failures_by_severity: Dict[str, int] = {}
        for ep in episodes:
            for failure in ep.failures:
                failures_by_severity[failure.severity] = (
                    failures_by_severity.get(failure.severity, 0) + 1
                )

        # Compute metric distributions
        metric_distributions = self._compute_metric_distributions(episodes)

        # Check robustness at profile level (cross-scenario)
        robustness_evaluator = self.evaluators.get("robustness")
        if robustness_evaluator and isinstance(robustness_evaluator, RobustnessEvaluator):
            robustness_failures = robustness_evaluator.evaluate_profile(
                episodes, agent.agent_id, agent.version
            )
            if robustness_failures:
                # Add robustness failures to the count
                for failure in robustness_failures:
                    failures_by_dimension[failure.dimension] = (
                        failures_by_dimension.get(failure.dimension, 0) + 1
                    )
                    failures_by_severity[failure.severity] = (
                        failures_by_severity.get(failure.severity, 0) + 1
                    )
                total_failures += len(robustness_failures)

        return StaticAgentProfile(
            agent_id=agent.agent_id,
            agent_version=agent.version,
            evaluation_run_id=self.run_id,
            episodes_evaluated=len(episodes),
            episodes_with_failures=episodes_with_failures,
            total_failures=total_failures,
            failures_by_dimension=failures_by_dimension,
            failures_by_severity=failures_by_severity,
            metric_distributions=metric_distributions,
            dimensions_evaluated=list(self.evaluators.keys()),
            scenario_ids=[ep.scenario_id for ep in episodes],
            holdout_used=False,  # Phase 2 never uses holdout for baseline
        )

    def _compute_metric_distributions(
        self, episodes: List[EpisodeEvaluation]
    ) -> Dict[str, Dict[str, float]]:
        """Compute distribution statistics for each metric across episodes."""
        metric_values: Dict[str, List[float]] = {}

        for ep in episodes:
            for metric_name, value in ep.metrics.items():
                if value is not None and isinstance(value, (int, float)):
                    if metric_name not in metric_values:
                        metric_values[metric_name] = []
                    metric_values[metric_name].append(float(value))

        distributions = {}
        for metric_name, values in metric_values.items():
            if len(values) >= 2:
                sorted_values = sorted(values)
                distributions[metric_name] = {
                    "min": min(values),
                    "max": max(values),
                    "mean": statistics.fmean(values),
                    "median": statistics.median(values),
                    "p95": sorted_values[int(len(sorted_values) * 0.95)],
                }
            elif len(values) == 1:
                distributions[metric_name] = {
                    "min": values[0],
                    "max": values[0],
                    "mean": values[0],
                    "median": values[0],
                    "p95": values[0],
                }

        return distributions

    def run(self, agents: List[BaseTradingAgent]) -> StaticEvaluationResult:
        """Execute complete static evaluation for all agents.

        Args:
            agents: List of agents to evaluate

        Returns:
            Complete StaticEvaluationResult with all profiles and episodes
        """
        agent_profiles = []

        for agent in agents:
            profile = self.evaluate_agent(agent)
            agent_profiles.append(profile)

        # Create final result
        result = StaticEvaluationResult(
            run_id=self.run_id,
            experiment_id=self.experiment_id,
            description=self.description,
            agent_profiles=agent_profiles,
            episode_evaluations=self.episode_evaluations,
            scenario_ids=[s.scenario_id for s in self.baseline_scenarios],
            scenario_source_splits=[s.source_split for s in self.baseline_scenarios],
            holdout_scenario_ids=[s.scenario_id for s in self.holdout_scenarios],
            configuration=self.config,
            total_episodes=len(self.episode_evaluations),
            total_failures=sum(len(ep.failures) for ep in self.episode_evaluations),
            dimensions=list(self.evaluators.keys()),
            started_at=self.started_at,
        )

        return result

    def save_result(self, result: StaticEvaluationResult, output_dir: Optional[str] = None):
        """Save evaluation result to disk.

        Args:
            result: The evaluation result to save
            output_dir: Output directory (defaults to config's results_dir)
        """
        import json

        if output_dir is None:
            output_dir = self.config["output"]["results_dir"]

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Save complete result as JSON
        result_file = output_path / f"{result.run_id}_result.json"
        with open(result_file, "w") as f:
            json.dump(result.to_dict(), f, indent=2, default=str)

        # Save episode evaluations as JSONL
        if self.config["output"].get("save_trajectories", True):
            episodes_file = output_path / f"{result.run_id}_episodes.jsonl"
            with open(episodes_file, "w") as f:
                for ep in result.episode_evaluations:
                    f.write(json.dumps(ep.model_dump(), default=str) + "\n")

        # Save agent profiles as JSON
        if self.config["output"].get("save_agent_profiles", True):
            profiles_file = output_path / f"{result.run_id}_profiles.json"
            with open(profiles_file, "w") as f:
                json.dump(
                    [p.model_dump() for p in result.agent_profiles],
                    f,
                    indent=2,
                    default=str,
                )

        return result_file
