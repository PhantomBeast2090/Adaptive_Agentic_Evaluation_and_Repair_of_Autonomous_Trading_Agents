import types

from src.schemas.scenario import StaticScenario
from src.schemas.static_evaluation import EpisodeEvaluation
from evaluation.adaptive.runner import AdaptiveRunner


class DummyAgent:
    def __init__(self, agent_id="agentA", version="v1"):
        self.agent_id = agent_id
        self.version = version


def make_scenario(sid):
    return StaticScenario(
        scenario_id=sid,
        source_split="discovery",
        market_data_path="/tmp",
        start_date="2020-01-01",
        end_date="2020-03-01",
        dimension="risk",
        difficulty="medium",
        market_regime="volatile",
        initial_cash=100000.0,
        transaction_cost_bps=1.0,
        holdout=False,
        description="",
    )


def test_seed_propagated_through_evaluate_callable():
    """Runner seed must reach the evaluation callable via the existing seed kwarg."""
    pool = [make_scenario("s1"), make_scenario("s2"), make_scenario("s3")]
    seen_seeds = []

    def capturing_evaluate(agent, scenario, seed=None):
        seen_seeds.append(seed)
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
            seed=seed,
        )

    # Bind like StaticEvaluator.evaluate_on_scenario (bound method path)
    class FakeEvaluator:
        def evaluate_on_scenario(self, agent, scenario, seed=None):
            return capturing_evaluate(agent, scenario, seed=seed)

    evaluator = FakeEvaluator()
    runner = AdaptiveRunner(pool, seed=777, evaluate_callable=evaluator.evaluate_on_scenario)
    report = runner.run(DummyAgent(), initial_samples=1, budget=2, batch_size=1, strategy="random")

    assert seen_seeds, "evaluate callable was never invoked"
    assert all(s == 777 for s in seen_seeds), f"seed not propagated: {seen_seeds}"
    for ep in report["episodes"]:
        assert ep.seed == 777


def test_selection_metadata_recorded():
    pool = [
        StaticScenario(
            scenario_id="s1", source_split="discovery", market_data_path="/tmp",
            start_date="2020-01-01", end_date="2020-03-01", dimension="risk",
            difficulty="hard", market_regime="volatile", initial_cash=100000.0,
            transaction_cost_bps=1.0, holdout=False, description="",
        ),
        StaticScenario(
            scenario_id="s2", source_split="discovery", market_data_path="/tmp",
            start_date="2020-04-01", end_date="2020-06-01", dimension="risk",
            difficulty="easy", market_regime="stable", initial_cash=100000.0,
            transaction_cost_bps=1.0, holdout=False, description="",
        ),
        StaticScenario(
            scenario_id="s3", source_split="discovery", market_data_path="/tmp",
            start_date="2020-07-01", end_date="2020-09-01", dimension="risk",
            difficulty="medium", market_regime="volatile", initial_cash=100000.0,
            transaction_cost_bps=1.0, holdout=False, description="",
        ),
    ]

    from src.schemas.static_evaluation import FailureRecord

    def fake_eval(self, agent, scenario):
        if scenario.market_regime == "volatile":
            f = FailureRecord(
                dimension="risk", metric_name="max_drawdown", observed_value=0.3,
                threshold=0.2, threshold_direction="above",
                episode_id=f"ep_{scenario.scenario_id}", scenario_id=scenario.scenario_id,
                severity="high", evidence="drawdown exceeded",
            )
            return EpisodeEvaluation(
                episode_id=f"ep_{scenario.scenario_id}", scenario_id=scenario.scenario_id,
                agent_id=agent.agent_id, agent_version=agent.version,
                trajectory_digest="d", metrics={"max_drawdown": 0.3}, failures=[f],
                dimensions_evaluated=["risk"], dimensions_passed=[], dimensions_failed=["risk"],
            )
        return EpisodeEvaluation(
            episode_id=f"ep_{scenario.scenario_id}", scenario_id=scenario.scenario_id,
            agent_id=agent.agent_id, agent_version=agent.version,
            trajectory_digest="d", metrics={}, failures=[],
            dimensions_evaluated=["risk"], dimensions_passed=["risk"], dimensions_failed=[],
        )

    runner = AdaptiveRunner(pool, seed=42)
    runner._evaluate_episode = types.MethodType(fake_eval, runner)
    report = runner.run(DummyAgent(), initial_samples=1, budget=3, batch_size=1, strategy="adaptive")

    assert report["seed"] == 42
    assert report["strategy"] == "adaptive"
    assert report["budget"] == 3
    assert len(report["scenario_sequence"]) == report["evaluated_count"]
    assert len(report["selection_history"]) == report["evaluated_count"]
    for entry in report["selection_history"]:
        assert entry["scenario_id"]
        assert entry["reason"]
        assert "rank" in entry and "score" in entry
    # At least one non-initial adaptive selection with a numeric score
    adaptive_picks = [e for e in report["selection_history"] if e["phase"] == "selection"]
    assert adaptive_picks


def test_seed_reaches_trajectory_via_static_evaluator(monkeypatch):
    """End of chain: StaticEvaluator seed arg must reach Trajectory.seed."""
    from evaluation.static_evaluator import StaticEvaluator
    import evaluation.static_evaluator as static_mod
    from evaluation.episode_runner import Trajectory

    static_eval = StaticEvaluator(config_path="configs/static_evaluation.yaml")
    captured = {}

    real_run_episode = static_mod.run_episode

    def capturing_run_episode(agent, environment, scenario_id, episode_id=None, seed=None, **kwargs):
        captured["seed"] = seed
        traj = real_run_episode(
            agent=agent, environment=environment, scenario_id=scenario_id,
            episode_id=episode_id, seed=seed,
        )
        assert traj.seed == seed
        return traj

    monkeypatch.setattr(static_mod, "run_episode", capturing_run_episode)

    scenario = static_eval.baseline_scenarios[0]
    agent = DummyAgent(agent_id="seed_probe", version="v1")
    # Minimal act/reset for the probe agent
    agent.act = lambda obs: {"action": "HOLD", "quantity": 0.0}
    agent.reset = lambda: None
    ep = static_eval.evaluate_on_scenario(agent, scenario, seed=555)
    assert captured["seed"] == 555
    assert ep.seed == 555
