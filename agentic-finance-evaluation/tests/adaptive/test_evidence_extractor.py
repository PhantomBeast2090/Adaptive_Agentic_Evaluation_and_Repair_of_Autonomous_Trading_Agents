from src.schemas.static_evaluation import EpisodeEvaluation, FailureRecord
from evaluation.adaptive.evidence_extractor import extract_vulnerabilities_from_episode


def test_extract_single_failure_to_vulnerability():
    failure = FailureRecord(
        dimension="risk",
        metric_name="max_drawdown",
        observed_value=0.35,
        threshold=0.2,
        threshold_direction="above",
        episode_id="ep1",
        scenario_id="s1",
        severity="high",
        evidence="max_drawdown exceeded threshold",
    )

    ep = EpisodeEvaluation(
        episode_id="ep1",
        scenario_id="s1",
        agent_id="agentX",
        agent_version="v1",
        trajectory_digest="digest",
        metrics={"max_drawdown": 0.35},
        failures=[failure],
        dimensions_evaluated=["risk"],
        dimensions_passed=[],
        dimensions_failed=["risk"],
    )

    vulns = extract_vulnerabilities_from_episode(ep, scenario_meta={"market_regime": "volatile", "difficulty": "hard"})
    assert len(vulns) == 1
    v = vulns[0]
    assert v.vuln_id.startswith("ep1:")
    assert v.category == "risk"
    assert v.subtype == "max_drawdown"
    assert v.metrics.get("max_drawdown") == 0.35
    assert v.affected_regimes == ["volatile"]
    assert v.affected_difficulty == "hard"
