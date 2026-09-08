import pytest

from src.schemas.scenario import StaticScenario
from evaluation.adaptive.runner import AdaptiveRunner


def make_scenario(sid, holdout=False, source_split="discovery"):
    return StaticScenario(
        scenario_id=sid,
        source_split=source_split,
        market_data_path="/tmp",
        start_date="2020-01-01",
        end_date="2020-03-01",
        dimension="risk",
        difficulty="medium",
        market_regime="volatile",
        initial_cash=100000.0,
        transaction_cost_bps=1.0,
        holdout=holdout,
        description="",
    )


def test_holdout_true_rejected():
    pool = [make_scenario("s1", holdout=False), make_scenario("s2", holdout=True)]
    with pytest.raises(ValueError, match="Holdout"):
        AdaptiveRunner(pool, seed=0)


def test_ood_source_split_rejected_even_if_flag_false():
    pool = [make_scenario("s1"), make_scenario("ood_1", holdout=False, source_split="ood_validation")]
    with pytest.raises(ValueError, match="[Oo][Oo][Dd]|[Hh]oldout"):
        AdaptiveRunner(pool, seed=0)


def test_clean_discovery_pool_accepted():
    pool = [make_scenario("s1"), make_scenario("s2")]
    runner = AdaptiveRunner(pool, seed=0)
    assert len(runner.scenario_pool) == 2
