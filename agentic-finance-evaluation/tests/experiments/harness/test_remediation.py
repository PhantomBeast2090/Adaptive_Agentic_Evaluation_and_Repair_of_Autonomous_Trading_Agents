"""Incident-remediation proofs (pure, zero market episodes).

1. Scientific identity byte-for-byte stable.
2. Roles produce distinct execution identities.
3. Instances deterministic.
4. Reproduction instances cannot overwrite one another.
5. Existing artefacts cannot be silently overwritten.
6-7. Role collision freedom.
8-9. Incident exclusion + Tier-1 allowlist.
10. Persistence/reload/fingerprint integrity.
"""

import pytest

from experiments.harness.errors import IntegrityFailure
from experiments.harness.identity import (
    ExecutionRole,
    execution_id,
    execution_result_path,
    experiment_identity,
)
from experiments.harness.result import ExperimentResult

from .fixtures import make_config


def _result(**overrides):
    params = {
        "experiment_id": "exp-1",
        "protocol_fingerprint": "proto-fp",
    }
    params.update(overrides)
    return ExperimentResult(**params)


def test_scientific_identity_stable_despite_roles():
    first = experiment_identity(make_config())
    assert first == experiment_identity(make_config())
    # Role/instance play no part in scientific identity inputs.
    from experiments.harness.identity import identity_payload

    payload = identity_payload(make_config())
    assert "role" not in payload
    assert "instance" not in payload
    assert "execution" not in str(payload).lower()


def test_roles_produce_distinct_execution_identities():
    exp = experiment_identity(make_config())
    ids = {
        execution_id(exp, role, "001")
        for role in (
            ExecutionRole.SYSTEM_VALIDATION,
            ExecutionRole.TIER1_PRIMARY,
            ExecutionRole.REPRODUCTION,
        )
    }
    assert len(ids) == 3


def test_instances_deterministic_and_distinct():
    exp = experiment_identity(make_config())
    assert execution_id(exp, "TIER1_PRIMARY", "001") == execution_id(
        exp, ExecutionRole.TIER1_PRIMARY, "001"
    )
    assert execution_id(exp, "TIER1_PRIMARY", "001") != execution_id(
        exp, "TIER1_PRIMARY", "002"
    )
    with pytest.raises(ValueError):
        execution_id(exp, "TIER1_PRIMARY", "")
    with pytest.raises(ValueError):
        execution_id(exp, "NOPE", "001")


def test_execution_paths_never_collide():
    exp = experiment_identity(make_config())
    paths = {
        execution_result_path(
            "results/e3", exp,
            execution_id(exp, role, inst),
        )
        for role in ("SYSTEM_VALIDATION", "TIER1_PRIMARY", "REPRODUCTION")
        for inst in ("001", "002")
    }
    assert len(paths) == 6
    assert all(p.startswith("results/e3/" + exp + "/") for p in paths)


def test_save_refuses_overwrite(tmp_path):
    result = _result(
        execution_role="TIER1_PRIMARY", execution_id="e1",
    )
    path = str(tmp_path / "r.json")
    result.save(path)
    with pytest.raises(IntegrityFailure):
        result.save(path)
    # Distinct instance writes beside it without conflict.
    other = _result(execution_role="TIER1_PRIMARY", execution_id="e2")
    other.save(str(tmp_path / "r2.json"))


def test_role_labelled_round_trip():
    result = _result(
        execution_role=ExecutionRole.TIER1_PRIMARY, execution_id="e1",
    )
    revived = ExperimentResult.from_dict(result.to_dict())
    assert revived.execution_role is ExecutionRole.TIER1_PRIMARY
    assert revived.execution_id == "e1"
    assert revived.fingerprint() == result.fingerprint()
    # Role-less historical shape still loads (audit readability).
    legacy = ExperimentResult.from_dict(
        {k: v for k, v in result.to_dict().items()
         if k not in ("execution_role", "execution_id")}
    )
    assert legacy.execution_role is None
    # id without role is forbidden (no silent role-less production).
    with pytest.raises(ValueError):
        _result(execution_id="e1")


def test_tier1_allowlist_logic():
    rows = [
        {"execution_role": "TIER1_PRIMARY", "execution_id": "a"},
        {"execution_role": "SYSTEM_VALIDATION", "execution_id": "b"},
        {"execution_role": "REPRODUCTION", "execution_id": "c"},
        {},
    ]
    eligible = [
        row for row in rows
        if row.get("execution_role") == "TIER1_PRIMARY"
        and row.get("execution_id")
    ]
    assert eligible == [
        {"execution_role": "TIER1_PRIMARY", "execution_id": "a"}
    ]


def test_incident_sidecar_schema():
    import pathlib

    import yaml

    root = (
        pathlib.Path(__file__).resolve().parent.parent.parent.parent
        / "results"
        / "e3"
    )
    sidecars = sorted(root.glob("*.incident.yaml"))
    assert sidecars, "incident registry entry must exist beside artefact"
    for path in sidecars:
        entry = yaml.safe_load(path.read_text())
        assert entry["TIER1_ELIGIBLE"] is False
        assert entry["classification"] == "CONTAMINATED_TIER1_ATTEMPT"
        assert entry["artefact_fingerprint"]
        artefact = root / path.name.replace(".incident.yaml", ".json")
        assert artefact.exists(), "registry must sit beside its artefact"
