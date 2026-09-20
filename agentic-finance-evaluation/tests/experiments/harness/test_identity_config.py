"""Identity determinism, canonicalisation, configuration validation."""

import pytest

from experiments.harness.config import ExperimentConfig
from experiments.harness.errors import ManifestMismatchError
from experiments.harness.identity import (
    arm_identity,
    experiment_identity,
    identity_payload,
    result_path,
)

from .fixtures import HELD, make_config, make_manifest


def test_identical_configs_share_identity():
    assert experiment_identity(make_config()) == experiment_identity(
        make_config()
    )


def test_identity_changes_when_scientific_inputs_change():
    base = experiment_identity(make_config())
    assert experiment_identity(make_config(transaction_cost_bps=6.0)) != base
    assert experiment_identity(make_config(diagnostic_policy="adaptive")) != base
    assert experiment_identity(make_config(seed_provenance=8)) != base


def test_identity_payload_is_closed_and_canonical():
    payload = identity_payload(make_config())
    assert "wall_clock" not in str(payload).lower()
    assert payload["diagnostic_window"] == ["2023-05-15", "2023-06-15"]
    assert payload["arm"] == "N-D"


def test_arm_identities_deterministic_and_distinct():
    first = arm_identity("exp-1", "N-D")
    assert first == arm_identity("exp-1", "N-D")
    assert first != arm_identity("exp-1", "R-H")
    with pytest.raises(ValueError):
        arm_identity("exp-1", "H")


def test_result_path_deterministic():
    assert result_path("results/e3", "abc") == "results/e3/abc.json"
    assert result_path("results/e3/", "abc") == "results/e3/abc.json"


def test_config_rejects_bad_arms_policies_windows():
    with pytest.raises(ValueError):
        make_config(arm="H")
    with pytest.raises(ValueError):
        make_config(diagnostic_policy="clever")
    with pytest.raises(ValueError):
        make_config(heldout_window=("2023-05-20", "2023-06-10"))
    with pytest.raises(ValueError):
        make_config(transaction_cost_bps=-1.0)
    with pytest.raises(ValueError):
        make_config(universe={})


def test_config_round_trip():
    config = make_config()
    assert ExperimentConfig.from_dict(config.to_dict()).to_dict() == (
        config.to_dict()
    )
    with pytest.raises(ValueError):
        ExperimentConfig.from_dict({**config.to_dict(), "zzz": 1})


def test_manifest_verification_accepts_matching_config():
    make_config().verify_against_manifest(make_manifest())


def test_manifest_verification_rejects_mutations():
    base = make_manifest()
    cases = [
        ("temporal", {**base["temporal"], "diagnostic_start": "2020-01-01"}),
        ("temporal", {**base["temporal"], "heldout_end": "2023-08-11"}),
        (
            "environment",
            {**base["environment"], "transaction_cost_bps": 9.0},
        ),
        (
            "environment",
            {
                **base["environment"],
                "universe": {"nse_equity": ["RELIANCE:EQ"]},
            },
        ),
        ("budgets", {**base["budgets"], "max_tests": 4}),
        ("budgets", {**base["budgets"], "max_repairs": 0}),
        (
            "fixed_sequence",
            {"order": ["T-null", "T-cost2x"]},
        ),
        (
            "candidate_pool",
            [{"test_id": "T-null"}],
        ),
    ]
    for key, mutated in cases:
        mutated_manifest = dict(base)
        mutated_manifest[key] = mutated
        with pytest.raises(ManifestMismatchError):
            make_config().verify_against_manifest(mutated_manifest)
    with pytest.raises(ManifestMismatchError):
        make_config(benchmark_id="nope", agent_id="nope").verify_against_manifest(
            base
        )
