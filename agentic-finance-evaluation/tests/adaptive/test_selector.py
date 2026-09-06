from src.schemas.scenario import StaticScenario
from src.schemas.vulnerability import VulnerabilityRecord
from evaluation.adaptive.selector import rank_candidates


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


def test_rank_candidates_prefers_regime_and_difficulty():
    pool = [
        make_scenario("s1", "volatile", "hard"),
        make_scenario("s2", "stable", "easy"),
        make_scenario("s3", "volatile", "medium"),
    ]

    vuln = VulnerabilityRecord(
        vuln_id="v1",
        category="risk",
        subtype="max_drawdown",
        evidence=[],
        metrics={"max_drawdown": 0.4},
        triggering_condition="high drawdown",
        affected_regimes=["volatile"],
        affected_difficulty="hard",
        severity="high",
        provenance={"episode_id": "ep1", "scenario_id": "s1"},
    )

    ranked = rank_candidates(vuln, pool, top_k=3, seed=42)
    # Top should be s1 (matches regime + difficulty)
    assert ranked[0][0].scenario_id == "s1"
    # Next best should be s3 (matches regime)
    assert ranked[1][0].scenario_id == "s3"
