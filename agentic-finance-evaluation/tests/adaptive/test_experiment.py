import copy
import json

import pytest

from src.schemas.scenario import StaticScenario
from src.schemas.static_evaluation import EpisodeEvaluation, FailureRecord
from evaluation.adaptive.experiment import (
    build_candidate_pool,
    candidate_pool_fingerprint,
    dataset_fingerprint,
    load_adaptive_config,
    load_run_record,
    run_single_arm,
    save_run_record,
    validate_comparability,
)
from evaluation.adaptive.runner import AdaptiveRunner


class DummyAgent:
    def __init__(self, agent_id="agentA", version="v1"):
        self.agent_id = agent_id
        self.version = version


def make_pool():
    def sc(sid, regime="volatile", difficulty="medium"):
        return StaticScenario(
            scenario_id=sid, source_split="discovery", market_data_path="/tmp",
            start_date="2020-01-01", end_date="2020-03-01", dimension="risk",
            difficulty=difficulty, market_regime=regime, initial_cash=100000.0,
            transaction_cost_bps=1.0, holdout=False, description="",
        )
    return [sc("s1"), sc("s2", "stable", "easy"), sc("s3")]


def fake_evaluate(agent, scenario, seed=None):
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
            seed=seed,
        )
    return EpisodeEvaluation(
        episode_id=f"ep_{scenario.scenario_id}", scenario_id=scenario.scenario_id,
        agent_id=agent.agent_id, agent_version=agent.version,
        trajectory_digest="d", metrics={}, failures=[],
        dimensions_evaluated=["risk"], dimensions_passed=["risk"], dimensions_failed=[],
        seed=seed,
    )


class FakeEvaluator:
    def evaluate_on_scenario(self, agent, scenario, seed=None):
        return fake_evaluate(agent, scenario, seed=seed)


def test_pool_fingerprint_deterministic_and_order_independent():
    pool = make_pool()
    fp1 = candidate_pool_fingerprint(pool)
    fp2 = candidate_pool_fingerprint(list(reversed(pool)))
    assert fp1 == fp2
    assert len(fp1) == 64
    altered = copy.deepcopy(pool)
    altered[0] = altered[0].model_copy(update={"difficulty": "hard"})
    assert candidate_pool_fingerprint(altered) != fp1
    # No transient fields: fingerprint stable across calls
    assert candidate_pool_fingerprint(pool) == fp1


def test_dataset_fingerprint_synthetic_pool_stable():
    pool = make_pool()
    assert dataset_fingerprint(pool) == dataset_fingerprint(pool)


def test_build_candidate_pool_discovery_only():
    config = load_adaptive_config("configs/adaptive_evaluation.yaml")
    pool = build_candidate_pool(config, base_dir=".")
    assert len(pool) > 0
    for s in pool:
        assert s.holdout is False
        assert s.source_split == "discovery"
    # Deterministic ordering
    assert [s.scenario_id for s in pool] == sorted(s.scenario_id for s in pool)


def test_single_arm_provenance_and_persistence(tmp_path):
    pool = make_pool()
    evaluator = FakeEvaluator()
    pool_fp = candidate_pool_fingerprint(pool)
    dataset_fp = dataset_fingerprint(pool)
    agent = DummyAgent()
    record = run_single_arm(
        pool=pool, agent=agent, seed=42, strategy="adaptive",
        budget=3, initial_samples=1, batch_size=1,
        evaluate_callable=evaluator.evaluate_on_scenario,
        experiment_id="test_exp", description="test",
        configuration={"agents": [{"agent_id": "agentA", "version": "v1",
                                   "class": "DummyAgent", "module": "test"}]},
        git_commit="abc123", dataset_fp=dataset_fp, pool_fp=pool_fp,
    )
    assert record.strategy == "adaptive"
    assert record.seed == 42
    assert record.budget == 3
    assert record.dataset_fingerprint == dataset_fp
    assert record.pool_fingerprint == pool_fp
    assert len(record.scenario_sequence) == record.evaluated_count
    assert len(record.selection_history) == record.evaluated_count
    assert record.episode_evaluations
    assert record.git_commit == "abc123"

    path = save_run_record(record, str(tmp_path))
    assert path.exists()
    reloaded = load_run_record(str(path))
    assert reloaded.strategy == record.strategy
    assert reloaded.seed == record.seed
    assert reloaded.budget == record.budget
    assert reloaded.pool_fingerprint == record.pool_fingerprint
    assert reloaded.dataset_fingerprint == record.dataset_fingerprint
    assert reloaded.scenario_sequence == record.scenario_sequence
    assert len(reloaded.selection_history) == len(record.selection_history)
    # JSON round-trip preserves required metadata
    raw = json.loads(path.read_text())
    for key in ("strategy", "seed", "budget", "pool_fingerprint", "dataset_fingerprint",
                "scenario_sequence", "selection_history", "vulnerabilities"):
        assert key in raw


def test_paired_arms_share_pool_budget_seed():
    pool = make_pool()
    evaluator = FakeEvaluator()
    pool_fp = candidate_pool_fingerprint(pool)
    dataset_fp = dataset_fingerprint(pool)
    agent = DummyAgent()
    adaptive = run_single_arm(
        pool=pool, agent=agent, seed=7, strategy="adaptive",
        budget=3, initial_samples=1, batch_size=1,
        evaluate_callable=evaluator.evaluate_on_scenario,
        experiment_id="test_exp", configuration={}, git_commit="c",
        dataset_fp=dataset_fp, pool_fp=pool_fp,
    )
    random = run_single_arm(
        pool=pool, agent=agent, seed=7, strategy="random",
        budget=3, initial_samples=1, batch_size=1,
        evaluate_callable=evaluator.evaluate_on_scenario,
        experiment_id="test_exp", configuration={}, git_commit="c",
        dataset_fp=dataset_fp, pool_fp=pool_fp,
    )
    # Mechanically comparable: must not raise
    validate_comparability(adaptive, random)
    assert adaptive.pool_fingerprint == random.pool_fingerprint
    assert adaptive.dataset_fingerprint == random.dataset_fingerprint
    assert adaptive.budget == random.budget == 3
    assert adaptive.seed == random.seed == 7


def test_comparability_rejects_mismatch():
    pool = make_pool()
    evaluator = FakeEvaluator()
    pool_fp = candidate_pool_fingerprint(pool)
    dataset_fp = dataset_fingerprint(pool)
    agent = DummyAgent()
    adaptive = run_single_arm(
        pool=pool, agent=agent, seed=7, strategy="adaptive",
        budget=3, initial_samples=1, batch_size=1,
        evaluate_callable=evaluator.evaluate_on_scenario,
        experiment_id="test_exp", configuration={}, git_commit="c",
        dataset_fp=dataset_fp, pool_fp=pool_fp,
    )
    other_pool = make_pool()[:-1]  # different pool size/content
    other_fp = candidate_pool_fingerprint(other_pool)
    random = run_single_arm(
        pool=other_pool, agent=agent, seed=7, strategy="random",
        budget=2, initial_samples=1, batch_size=1,
        evaluate_callable=evaluator.evaluate_on_scenario,
        experiment_id="test_exp", configuration={}, git_commit="c",
        dataset_fp=dataset_fingerprint(other_pool), pool_fp=other_fp,
    )
    with pytest.raises(ValueError):
        validate_comparability(adaptive, random)


def test_end_to_end_paired_experiment_small(tmp_path):
    """Small controlled Adaptive-vs-Random run with injected fake evaluator."""
    from evaluation.adaptive.experiment import run_paired_experiment

    def factory(strategy, seed, agent):
        evaluator = FakeEvaluator()
        return evaluator.evaluate_on_scenario

    summary = run_paired_experiment(
        config_path="configs/adaptive_evaluation.yaml",
        base_dir=".",
        output_dir=str(tmp_path),
        evaluate_callable_factory=factory,
    )
    assert summary["pairs"], "no pairs executed"
    strategies = {p["strategy"] for p in summary["pairs"]}
    assert {"adaptive", "random"} <= strategies
    # Paired fingerprints must match within each (agent, seed)
    from collections import defaultdict
    by_pair = defaultdict(dict)
    for p in summary["pairs"]:
        by_pair[(p["agent_id"], p["seed"])][p["strategy"]] = p
    for key, arms in by_pair.items():
        if "adaptive" in arms and "random" in arms:
            a = load_run_record(arms["adaptive"]["file"])
            r = load_run_record(arms["random"]["file"])
            validate_comparability(a, r)
