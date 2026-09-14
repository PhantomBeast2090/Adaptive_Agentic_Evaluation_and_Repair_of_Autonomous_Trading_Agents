"""E1 determinism + budget tests."""

import pytest

from evaluation.baseline import BaselineConfig, run_baseline
from evaluation.baseline.results import BaselineResult
from evaluation.contracts.budget import EvaluationBudget
from evaluation.contracts.stopping import StoppingReason

from .stubs import BuyOnceAgent, HoldAgent, small_config


def test_repeated_evaluation_is_deterministic():
    first = run_baseline(HoldAgent(), small_config("E1-DET-01"))
    second = run_baseline(HoldAgent(), small_config("E1-DET-01"))
    assert first.fingerprint() == second.fingerprint()
    assert first.to_dict() == second.to_dict()
    assert BaselineResult.from_dict(first.to_dict()) == first


def test_identity_sensitivity():
    base = run_baseline(HoldAgent(), small_config("E1-DET-02"))
    versioned = run_baseline(
        BuyOnceAgent(), small_config("E1-DET-02")
    )
    assert versioned.fingerprint() != base.fingerprint()
    narrower = run_baseline(
        HoldAgent(),
        small_config(
            "E1-DET-02",
            universe={
                "nse_equity": ["RELIANCE:EQ"],
                "mcx_gold": ["GOLDAUG2023"],
            },
        ),
    )
    assert narrower.fingerprint() != base.fingerprint()
    shorter = run_baseline(
        HoldAgent(),
        small_config("E1-DET-02", end_date="2023-05-19"),
    )
    assert shorter.fingerprint() != base.fingerprint()
    assert len(shorter.decision_records) < len(base.decision_records)


def test_budget_enforcement_and_usage():
    refused = small_config(
        "E1-DET-03",
        budget=EvaluationBudget(0, None, None, None, None),
    )
    with pytest.raises(ValueError):
        run_baseline(HoldAgent(), refused)
    result = run_baseline(HoldAgent(), small_config("E1-DET-04"))
    assert dict(result.budget_usage) == {"episodes": 1}
    assert result.stopping_reason is StoppingReason.NO_ACTIONABLE_FAILURE
    assert (
        result.evaluation_state.stopping_reason
        is StoppingReason.NO_ACTIONABLE_FAILURE
    )
    # E1 never emits repair/diagnosis lifecycle vocabulary.
    assert result.stopping_reason not in (
        StoppingReason.HYPOTHESIS_UNRESOLVED,
        StoppingReason.REPAIR_FAILED,
        StoppingReason.REGRESSION_DETECTED,
    )


def test_config_serialization_and_env_rendering():
    config = small_config("E1-DET-05", seed=7)
    assert BaselineConfig.from_dict(config.to_dict()) == config
    assert BaselineConfig.from_dict(config.to_dict()).fingerprint() == (
        config.fingerprint()
    )
    env_config = config.to_env_config()
    assert env_config["universe"]["nse_equity"] == ["RELIANCE:EQ", "TCS:EQ"]
    assert env_config["start_date"] == "2023-05-15"
    with pytest.raises(ValueError):
        small_config("E1-DET-05b", start_date="2023-05-26", end_date="2023-05-15")
    with pytest.raises(ValueError):
        small_config("E1-DET-05c", universe={})
