"""Provider boundary tests: rule table, determinism, read-only posture."""

import pytest

from evaluation.contracts.agent import AgentIdentity
from evaluation.diagnostics.repair.provider import (
    DEFAULT_RATIONALE,
    PROVIDER_METHOD,
    PROVIDER_VERSION,
    RULE_TABLE,
    DeterministicRuleProvider,
)

_HYP = {
    "hypothesis_id": "H-1",
    "hypothesis_fingerprint": "hfp-1",
    "failure_class": "excessive_turnover",
    "evidence_refs": ("E-1",),
}


def _propose(provider, **overrides):
    params = {
        "repair_id": "repair-D-1-H-1",
        "diagnostic_id": "D-1",
        "baseline_evaluation_id": "B-1",
        "baseline_fingerprint": "bfp-1",
        "diagnostic_state_fingerprint": "dfp-1",
        "target_agent_identity": AgentIdentity("agent-1", "0.1"),
        "target_agent_fingerprint": "afp-1",
    }
    params.update(_HYP)
    params.update(overrides)
    return provider.propose(**params)


def test_rule_table_maps_failure_classes():
    provider = DeterministicRuleProvider()
    assert provider.deterministic is True
    assert (provider.method, provider.version) == (
        PROVIDER_METHOD, PROVIDER_VERSION,
    )
    assert (PROVIDER_METHOD, PROVIDER_VERSION) == ("rule-table", "v1")
    assert RULE_TABLE
    proposal = _propose(provider)
    assert proposal.target_metric == "turnover"
    assert proposal.target_direction.value == "DECREASE"
    assert proposal.method == "rule-table"
    assert proposal.method_version == "v1"
    assert proposal.to_dict()["parameters"]["rules"] == [
        {"type": "per_session_order_cap", "max_orders": 1}
    ]


def test_unknown_failure_class_uses_documented_fallback():
    provider = DeterministicRuleProvider()
    proposal = _propose(provider, failure_class="mysterious_wobble")
    assert proposal.to_dict()["parameters"]["rules"] == [
        {"type": "per_session_order_cap", "max_orders": 1}
    ]
    assert DEFAULT_RATIONALE.split(":")[0] in proposal.rationale


def test_proposals_are_deterministic():
    provider = DeterministicRuleProvider()
    assert _propose(provider).fingerprint() == _propose(provider).fingerprint()


def test_proposal_binds_target_agent_state():
    provider = DeterministicRuleProvider()
    assert _propose(provider).target_agent_fingerprint == "afp-1"
    other = _propose(provider, target_agent_fingerprint="afp-2")
    assert other.fingerprint() != _propose(provider).fingerprint()


def test_provider_does_not_mutate_inputs():
    from ..execution_fixtures import HoldAgent
    from evaluation.diagnostics.repair.application import fingerprint_agent

    provider = DeterministicRuleProvider()
    agent = HoldAgent()
    before = fingerprint_agent(agent, agent.identity)
    _propose(provider)
    assert fingerprint_agent(agent, agent.identity) == before
