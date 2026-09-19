"""RepairProposal contract tests: immutability, identity, validation."""

import pytest

from evaluation.contracts.agent import AgentIdentity
from evaluation.diagnostics.contracts.predictions import ExpectedDirection
from evaluation.diagnostics.repair.proposal import RepairProposal


def _proposal(**overrides):
    payload = {
        "repair_id": "repair-D-1-H-1",
        "diagnostic_id": "D-1",
        "baseline_evaluation_id": "B-1",
        "baseline_fingerprint": "bfp-1",
        "diagnostic_state_fingerprint": "dfp-1",
        "target_agent_identity": AgentIdentity("agent-1", "0.1"),
        "target_agent_fingerprint": "afp-1",
        "hypothesis_id": "H-1",
        "hypothesis_fingerprint": "hfp-1",
        "failure_class": "excessive_turnover",
        "evidence_refs": ("E-1", "E-2"),
        "target_metric": "turnover",
        "target_direction": ExpectedDirection.DECREASE,
        "method": "rule-table",
        "method_version": "v1",
        "parameters": {"rules": [{"type": "per_session_order_cap", "max_orders": 1}]},
        "rationale": "Throttle order flow for overtrading.",
        "provenance": {"provider": "DeterministicRuleProvider"},
    }
    payload.update(overrides)
    return RepairProposal(**payload)


def test_valid_proposal_and_fingerprint_stability():
    first = _proposal()
    second = _proposal()
    assert first.fingerprint() == second.fingerprint()
    assert first.to_dict()["target_direction"] == "DECREASE"


def test_required_identity_and_reference_fields():
    for field_name in (
        "repair_id",
        "diagnostic_id",
        "baseline_evaluation_id",
        "baseline_fingerprint",
        "diagnostic_state_fingerprint",
        "target_agent_fingerprint",
        "hypothesis_id",
        "hypothesis_fingerprint",
        "failure_class",
        "target_metric",
        "rationale",
    ):
        with pytest.raises(ValueError):
            _proposal(**{field_name: "  "})
    with pytest.raises(ValueError):
        _proposal(evidence_refs=())
    with pytest.raises(ValueError):
        _proposal(evidence_refs=("E-1", "E-1"))
    with pytest.raises(TypeError):
        _proposal(target_agent_identity="agent-1")


def test_target_direction_must_move():
    with pytest.raises(ValueError):
        _proposal(target_direction=ExpectedDirection.NO_CHANGE)
    with pytest.raises(ValueError):
        _proposal(target_direction="SIDEWAYS")


def test_parameters_and_provenance_frozen():
    proposal = _proposal(parameters={"rules": [{"max_orders": 1}]})
    with pytest.raises(TypeError):
        proposal.parameters["rules"] = []
    assert proposal.fingerprint() == _proposal(
        parameters={"rules": [{"max_orders": 1}]}
    ).fingerprint()


def test_serialisation_round_trip_and_unknown_fields():
    proposal = _proposal()
    restored = RepairProposal.from_dict(proposal.to_dict())
    assert restored == proposal
    assert restored.fingerprint() == proposal.fingerprint()
    with pytest.raises(ValueError):
        RepairProposal.from_dict({**proposal.to_dict(), "zzz": 1})
    with pytest.raises(TypeError):
        RepairProposal.from_dict("not-a-mapping")
