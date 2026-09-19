"""Application tests: copy-on-write isolation and failure taxonomy."""

import pytest

from evaluation.contracts.agent import AgentIdentity
from evaluation.diagnostics.repair.application import (
    ApplicationStatus,
    apply_repair,
    fingerprint_agent,
    snapshot_policy,
)
from evaluation.diagnostics.repair.proposal import RepairProposal

from ..execution_fixtures import HoldAgent
from ...baseline.stubs import ChurnAgent
from .test_proposal import _proposal


def _proposal_for(agent, **overrides):
    proposal = _proposal(**overrides)
    return RepairProposal(
        **{
            **proposal.to_dict(),
            "target_agent_identity": agent.identity,
            "target_agent_fingerprint": fingerprint_agent(
                agent, agent.identity
            ),
        }
    )


def test_snapshot_and_fingerprint_determinism():
    agent = ChurnAgent()
    first = fingerprint_agent(agent, agent.identity)
    assert fingerprint_agent(agent, agent.identity) == first
    assert snapshot_policy(agent)["class"] == "ChurnAgent"
    with pytest.raises(TypeError):
        snapshot_policy(None)


def test_apply_leaves_original_untouched():
    agent = ChurnAgent()
    before_fp = fingerprint_agent(agent, agent.identity)
    before_state = snapshot_policy(agent)
    proposal = _proposal_for(agent)
    candidate, application, live = apply_repair(proposal, agent)
    assert application.status is ApplicationStatus.APPLIED
    assert application.error is None
    assert fingerprint_agent(agent, agent.identity) == before_fp
    assert snapshot_policy(agent) == before_state
    assert candidate.parent_fingerprint == before_fp
    assert candidate.candidate_fingerprint != before_fp
    assert live is not candidate
    assert candidate.candidate_identity.agent_id == "churn-stub"
    assert candidate.candidate_identity.version != "0.1"


def test_candidate_is_valid_target_agent():
    from evaluation.contracts.agent import validate_target_agent

    agent = HoldAgent()
    proposal = _proposal_for(agent)
    _, _, live = apply_repair(proposal, agent)
    assert validate_target_agent(live) == []
    assert live.identity.agent_id == "hold-stub"
    assert live.identity.version.startswith("0.1+r")


def test_cap_rule_truncates_orders():
    orders = [
        {"asset_id": "a", "instrument": "i", "side": "BUY", "quantity": 1.0},
        {"asset_id": "a", "instrument": "i", "side": "BUY", "quantity": 2.0},
    ]

    class EchoAgent:
        identity = AgentIdentity("echo", "0.1")

        def reset(self):
            return None

        def act(self, observation):
            return list(orders)

    echo_proposal = _proposal_for(EchoAgent())
    _, _, capped = apply_repair(echo_proposal, EchoAgent())
    assert capped.act({}) == orders[:1]


def test_unknown_rule_fails_application_not_silently():
    agent = HoldAgent()
    proposal = _proposal_for(agent)
    bad = RepairProposal(
        **{
            **proposal.to_dict(),
            "target_agent_identity": agent.identity,
            "parameters": {"rules": [{"type": "telepathy"}]},
        }
    )
    candidate, application, live = apply_repair(bad, agent)
    assert application.status is ApplicationStatus.FAILED
    assert application.error
    assert candidate.status is ApplicationStatus.FAILED
    assert live is None
    assert fingerprint_agent(agent, agent.identity) == (
        proposal.target_agent_fingerprint
    )


def test_stale_proposal_rejected_before_touching_agent():
    agent = ChurnAgent()
    proposal = _proposal_for(agent)
    agent.calls = 999
    with pytest.raises(ValueError):
        apply_repair(proposal, agent)


def test_application_serialisation_round_trip():
    agent = HoldAgent()
    candidate, application, _ = apply_repair(_proposal_for(agent), agent)
    assert type(candidate).from_dict(candidate.to_dict()) == candidate
    assert type(application).from_dict(application.to_dict()) == application
    assert candidate.fingerprint()
    assert application.fingerprint()
    assert ApplicationStatus.from_str("APPLIED") is ApplicationStatus.APPLIED
    with pytest.raises(ValueError):
        ApplicationStatus.from_str("MAYBE")
