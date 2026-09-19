"""Determinism tests: identical replay implies identical chain."""

from evaluation.diagnostics.repair.application import apply_repair
from evaluation.diagnostics.repair.proposal import RepairProposal

from ..execution_fixtures import HoldAgent
from .fixtures import HoldStub
from .test_application import _proposal_for


def test_identical_replay_identical_chain():
    agent = HoldAgent()
    first = apply_repair(_proposal_for(agent), agent)
    second = apply_repair(_proposal_for(agent), agent)
    assert first[0].fingerprint() == second[0].fingerprint()
    assert first[1].fingerprint() == second[1].fingerprint()
    assert first[0].candidate_fingerprint == second[0].candidate_fingerprint


def test_material_change_alters_identity():
    agent = HoldAgent()
    first = _proposal_for(agent)
    altered = RepairProposal(
        **{**first.to_dict(), "target_agent_identity": agent.identity,
           "rationale": "A different documented reason."}
    )
    assert altered.fingerprint() != first.fingerprint()
    first_out = apply_repair(first, agent)
    second_out = apply_repair(altered, agent)
    assert first_out[0].candidate_id != second_out[0].candidate_id
    assert first_out[0].candidate_fingerprint != (
        second_out[0].candidate_fingerprint
    )


def test_nondeterministic_provider_flagged_not_claimed():
    from evaluation.diagnostics.repair.provider import (
        DeterministicRuleProvider,
        RepairProvider,
    )

    assert isinstance(
        getattr(RepairProvider, "deterministic", None), property
    )
    assert DeterministicRuleProvider.deterministic is True

    class SketchyProvider(DeterministicRuleProvider):
        deterministic = False

    assert SketchyProvider.deterministic is False


def test_hold_stub_repair_is_deterministic():
    agent = HoldStub()
    first = apply_repair(_proposal_for(agent), agent)
    agent2 = HoldStub()
    second = apply_repair(_proposal_for(agent2), agent2)
    assert first[0].fingerprint() == second[0].fingerprint()
