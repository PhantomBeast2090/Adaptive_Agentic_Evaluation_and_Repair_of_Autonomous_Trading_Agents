import copy

import pytest

from evaluation.adaptive.experiment import load_adaptive_config, validate_adaptive_config


def test_adaptive_config_loads():
    config = load_adaptive_config("configs/adaptive_evaluation.yaml")
    assert config["experiment_id"] == "adaptive_eval_001"
    assert config["candidate_pool"]["splits"] == ["discovery"]
    assert config["candidate_pool"]["require_discovery_only"] is True
    assert config["candidate_pool"]["require_holdout_exclusion"] is True
    assert config["evaluation"]["budget"] >= 1
    assert config["evaluation"]["initial_samples"] >= 1
    assert config["evaluation"]["batch_size"] >= 1
    assert len(config["evaluation"]["seeds"]) >= 1
    assert set(config["evaluation"]["strategies"]) <= {"adaptive", "random"}
    assert config["agents"]
    assert config["output"]["results_dir"]
    # Discovery-only: forbidden splits must not appear
    for forbidden in ("ood_validation", "re_evaluation"):
        assert forbidden not in config["candidate_pool"]["splits"]
    validate_adaptive_config(config)


def test_adaptive_config_rejects_ood_pool():
    config = load_adaptive_config("configs/adaptive_evaluation.yaml")
    bad = copy.deepcopy(config)
    bad["candidate_pool"]["splits"] = ["discovery", "ood_validation"]
    with pytest.raises(ValueError):
        validate_adaptive_config(bad)


def test_adaptive_config_rejects_reevaluation_pool():
    config = load_adaptive_config("configs/adaptive_evaluation.yaml")
    bad = copy.deepcopy(config)
    bad["candidate_pool"]["splits"] = ["re_evaluation"]
    with pytest.raises(ValueError):
        validate_adaptive_config(bad)


def test_adaptive_config_rejects_bad_budget():
    config = load_adaptive_config("configs/adaptive_evaluation.yaml")
    bad = copy.deepcopy(config)
    bad["evaluation"]["budget"] = 0
    with pytest.raises(ValueError):
        validate_adaptive_config(bad)
    bad2 = copy.deepcopy(config)
    bad2["evaluation"]["initial_samples"] = bad2["evaluation"]["budget"] + 1
    with pytest.raises(ValueError):
        validate_adaptive_config(bad2)


def test_adaptive_config_rejects_empty_seeds():
    config = load_adaptive_config("configs/adaptive_evaluation.yaml")
    bad = copy.deepcopy(config)
    bad["evaluation"]["seeds"] = []
    with pytest.raises(ValueError):
        validate_adaptive_config(bad)
