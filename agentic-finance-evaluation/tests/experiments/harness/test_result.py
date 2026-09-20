"""Result artefact: provenance, serialisation, reproduction, RQ4 status."""

import pytest

from experiments.harness.result import (
    RQ4_DESCRIPTIVE_ONLY,
    ExperimentResult,
    RQ4Status,
)


def _minimal(**overrides):
    params = {
        "experiment_id": "exp-1",
        "protocol_fingerprint": "proto-fp",
    }
    params.update(overrides)
    return ExperimentResult(**params)


def test_round_trip_and_fingerprint_stability():
    result = _minimal(
        metrics_nd={"turnover": 2.0},
        delta_heldout={
            "baseline_original_heldout": "fp-nh",
            "repaired_heldout": "fp-rh",
            "turnover": {
                "reference": 2.0,
                "validation": 1.0,
                "delta": -1.0,
            },
        },
    )
    revived = ExperimentResult.from_dict(result.to_dict())
    assert revived.to_dict() == result.to_dict()
    assert revived.fingerprint() == result.fingerprint()
    assert result.rq4_status is RQ4Status.DESCRIPTIVE_ONLY_SINGLE_HYPOTHESIS


def test_unknown_fields_rejected():
    result = _minimal()
    with pytest.raises(ValueError):
        ExperimentResult.from_dict({**result.to_dict(), "zzz": 1})


def test_delta_heldout_requires_named_comparators():
    with pytest.raises(ValueError):
        _minimal(delta_heldout={"turnover": {}})


def test_save_load_round_trip(tmp_path):
    result = _minimal(metrics_rd={"turnover": 1.0})
    path = str(tmp_path / "exp-1.json")
    result.save(path)
    loaded = ExperimentResult.load(path)
    assert loaded.to_dict() == result.to_dict()
    assert loaded.fingerprint() == result.fingerprint()


def test_load_corrupt_file_fails_closed(tmp_path):
    from experiments.harness.errors import ProvenanceError

    path = tmp_path / "bad.json"
    path.write_text("{not json")
    with pytest.raises(ProvenanceError):
        ExperimentResult.load(str(path))


def test_operational_excluded_from_identity():
    plain = _minimal()
    assert plain.fingerprint() == ExperimentResult.from_dict(
        {**plain.to_dict(), "operational": {"ts": "2026-01-01"}}
    ).fingerprint()
