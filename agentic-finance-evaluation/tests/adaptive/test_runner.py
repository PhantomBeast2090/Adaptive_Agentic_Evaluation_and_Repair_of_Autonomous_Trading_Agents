import types

from src.schemas.scenario import StaticScenario
from evaluation.adaptive.runner import AdaptiveRunner
from src.schemas.static_evaluation import EpisodeEvaluation, FailureRecord


class DummyAgent:
    def __init__(self, agent_id="agentA", version="v1"):
        self.agent_id = agent_id
        self.version = version


def make_scenario(sid, regime, difficulty):
    return StaticScenario(
        scenario_id=sid,
        source_split="split",
        market_data_path="/tmp",
        start_date="2020-01-01",
        end_date="2020-03-01",
        dimension="risk",
        difficulty=difficulty,
        market_regime=regime,
        initial_cash=100000.0,
        transaction_cost_bps=1.0,
        holdout=False,
        description="",
    )


def _make_failure_for_scenario(scenario_id):
    return FailureRecord(
        dimension="risk",
        metric_name="max_drawdown",
        observed_value=0.3,
        threshold=0.2,
        threshold_direction="above",
        episode_id=f"ep_{scenario_id}",
        scenario_id=scenario_id,
        severity="high",
        evidence="drawdown exceeded",
    )


def test_adaptive_runner_adaptive_prefers_relevant_scenarios():
    # Create pool: s1 volatile/hard, s2 stable/easy, s3 volatile/medium
    pool = [
        make_scenario("s1", "volatile", "hard"),
        make_scenario("s2", "stable", "easy"),
        make_scenario("s3", "volatile", "medium"),
    ]

    runner = AdaptiveRunner(pool, seed=123)
    agent = DummyAgent()

    # Monkeypatch _evaluate_episode to return a failure only for volatile scenarios
    def fake_eval(self, agent, scenario):
        if scenario.market_regime == "volatile":
            failure = _make_failure_for_scenario(scenario.scenario_id)
            ep = EpisodeEvaluation(
                episode_id=f"ep_{scenario.scenario_id}",
                scenario_id=scenario.scenario_id,
                agent_id=agent.agent_id,
                agent_version=agent.version,
                trajectory_digest="d",
                metrics={"max_drawdown": 0.3},
                failures=[failure],
                dimensions_evaluated=["risk"],
                dimensions_passed=[],
                dimensions_failed=["risk"],
            )
            return ep
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

    runner._evaluate_episode = types.MethodType(fake_eval, runner)

    report = runner.run(agent, initial_samples=1, budget=3, batch_size=1, strategy="adaptive")
    # Should have evaluated up to 3 episodes
    assert report["evaluated_count"] <= 3
    # Should have discovered at least one vulnerability (volatile scenarios)
    assert report["unique_vulnerabilities"] >= 1


def test_adaptive_runner_random_baseline_is_deterministic():
    pool = [
        make_scenario("s1", "volatile", "hard"),
        make_scenario("s2", "stable", "easy"),
        make_scenario("s3", "volatile", "medium"),
    ]

    runner1 = AdaptiveRunner(pool, seed=999)
    runner2 = AdaptiveRunner(pool, seed=999)
    agent = DummyAgent()

    def fake_eval(self, agent, scenario):
        # No failures; just return an empty EpisodeEvaluation
        return EpisodeEvaluation(
            episode_id=f"ep_{scenario.scenario_id}",
            scenario_id=scenario.scenario_id,
            agent_id=agent.agent_id,
            agent_version=agent.version,
            trajectory_digest="d",
            metrics={},
            failures=[],
            dimensions_evaluated=[],
            dimensions_passed=[],
            dimensions_failed=[],
        )

    runner1._evaluate_episode = types.MethodType(fake_eval, runner1)
    runner2._evaluate_episode = types.MethodType(fake_eval, runner2)

    report1 = runner1.run(agent, initial_samples=1, budget=2, batch_size=1, strategy="random")
    report2 = runner2.run(agent, initial_samples=1, budget=2, batch_size=1, strategy="random")

    # Deterministic: same number evaluated and same scenario ids order
    ids1 = [ep.scenario_id for ep in report1["episodes"]]
    ids2 = [ep.scenario_id for ep in report2["episodes"]]
    assert ids1 == ids2
