import types

from src.data.scenario_loader import ScenarioLoader
from evaluation.static_evaluator import StaticEvaluator
from evaluation.adaptive.runner import AdaptiveRunner
# Use a lightweight dummy agent here to avoid heavy dependencies in tests


class DummyAgent:
    def __init__(self, agent_id="agentA", version="v1"):
        self.agent_id = agent_id
        self.version = version


def test_adaptive_end_to_end_with_static_evaluator(tmp_path, monkeypatch):
    # Build a tiny synthetic scenario pool (three scenarios) using StaticScenario
    # directly to avoid heavy data deps. Ensure none are holdout.
    from src.schemas.scenario import StaticScenario

    pool = [
        StaticScenario(
            scenario_id="s1",
            source_split="split",
            market_data_path="/tmp/data1.parquet",
            start_date="2020-01-01",
            end_date="2020-03-01",
            dimension="risk",
            difficulty="hard",
            market_regime="volatile",
            initial_cash=100000.0,
            transaction_cost_bps=1.0,
            holdout=False,
            description="",
        ),
        StaticScenario(
            scenario_id="s2",
            source_split="split",
            market_data_path="/tmp/data2.parquet",
            start_date="2020-04-01",
            end_date="2020-06-01",
            dimension="risk",
            difficulty="easy",
            market_regime="stable",
            initial_cash=100000.0,
            transaction_cost_bps=1.0,
            holdout=False,
            description="",
        ),
        StaticScenario(
            scenario_id="s3",
            source_split="split",
            market_data_path="/tmp/data3.parquet",
            start_date="2020-07-01",
            end_date="2020-09-01",
            dimension="risk",
            difficulty="medium",
            market_regime="volatile",
            initial_cash=100000.0,
            transaction_cost_bps=1.0,
            holdout=False,
            description="",
        ),
    ]

    # Create a StaticEvaluator but we will not call its full run; we will reuse
    # its evaluate_on_scenario method by binding it for use by AdaptiveRunner.
    static_eval = StaticEvaluator(config_path="configs/static_evaluation.yaml")

    # Create a deterministic dummy agent
    agent = DummyAgent(agent_id="synthA", version="v1")

    # Monkeypatch run_episode / environment to avoid actual market simulation.
    # We will monkeypatch StaticEvaluator.evaluate_on_scenario to return a
    # deterministic EpisodeEvaluation object per scenario.
    def fake_evaluate_on_scenario(self, agent, scenario, seed=None):
        # Create a minimal EpisodeEvaluation using existing FailureRecord
        from src.schemas.static_evaluation import EpisodeEvaluation, FailureRecord

        if scenario.market_regime == "volatile":
            f = FailureRecord(
                dimension="risk",
                metric_name="max_drawdown",
                observed_value=0.3,
                threshold=0.2,
                threshold_direction="above",
                episode_id=f"ep_{scenario.scenario_id}",
                scenario_id=scenario.scenario_id,
                severity="high",
                evidence="drawdown exceeded",
            )
            ep = EpisodeEvaluation(
                episode_id=f"ep_{scenario.scenario_id}",
                scenario_id=scenario.scenario_id,
                agent_id=agent.agent_id,
                agent_version=agent.version,
                trajectory_digest="d",
                metrics={"max_drawdown": 0.3},
                failures=[f],
                dimensions_evaluated=["risk"],
                dimensions_passed=[],
                dimensions_failed=["risk"],
            )
        else:
            ep = EpisodeEvaluation(
                episode_id=f"ep_{scenario.scenario_id}",
                scenario_id=scenario.scenario_id,
                agent_id=agent.agent_id,
                agent_version=agent.version,
                trajectory_digest="d",
                metrics={"max_drawdown": 0.0},
                failures=[],
                dimensions_evaluated=["risk"],
                dimensions_passed=["risk"],
                dimensions_failed=[],
            )

        return ep

    monkeypatch.setattr(static_eval, "evaluate_on_scenario", types.MethodType(fake_evaluate_on_scenario, static_eval))

    # Bind the static evaluator method to AdaptiveRunner via evaluate_callable
    runner = AdaptiveRunner(pool, seed=42, evaluate_callable=static_eval.evaluate_on_scenario)

    # Run adaptive strategy with budget 2 (should only evaluate up to 2 additional scenarios)
    report = runner.run(agent, initial_samples=1, budget=2, batch_size=1, strategy="adaptive")

    assert report["evaluated_count"] <= 2
    # Ensure vulnerabilities only come from non-holdout scenarios and are consistent
    for v in report["vulnerabilities"]:
        assert v.provenance["scenario_id"] in {"s1", "s2", "s3"}
    # Ensure deterministic with same seed
    runner2 = AdaptiveRunner(pool, seed=42, evaluate_callable=static_eval.evaluate_on_scenario)
    report2 = runner2.run(agent, initial_samples=1, budget=2, batch_size=1, strategy="adaptive")
    assert report["evaluated_count"] == report2["evaluated_count"]
