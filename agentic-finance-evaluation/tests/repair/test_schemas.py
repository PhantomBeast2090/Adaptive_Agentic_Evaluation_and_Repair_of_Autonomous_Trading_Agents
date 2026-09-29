"""Tier 1: schema validation, fingerprints, round-trips, LearnedContext render."""

import pytest

from evaluation.repair.schemas import (
    APPROVED_RULE_TYPES,
    FailureMechanism,
    MemoryEntry,
    RepairAuditRecord,
    RepairCandidate,
    RepairScope,
    RepairSpec,
    RepairVerification,
    RepairVersion,
)


def _mechanism(**over):
    base = {
        "mechanism_id": "mech-001",
        "taxonomy": "turnover",
        "condition": ("exposure=high",),
        "evidence_refs": ("eval-001",),
        "provenance": {"evaluation_id": "eval-001"},
    }
    base.update(over)
    return FailureMechanism(**base)


def _spec(**over):
    base = {
        "spec_id": "spec-001",
        "mechanism_fingerprint": "mfp",
        "rule_type": "per_session_order_cap",
        "rule_params": {"max_orders": 1},
    }
    base.update(over)
    return RepairSpec(**base)


def test_failure_mechanism_requires_evidence_and_provenance():
    with pytest.raises(ValueError):
        _mechanism(evidence_refs=())
    with pytest.raises(ValueError):
        _mechanism(provenance={})
    with pytest.raises(ValueError):
        _mechanism(trigger_hint=(("bogus_field", "gt", 1.0),))
    with pytest.raises(ValueError):
        _mechanism(trigger_hint=(("vix", "approx", 25.0),))
    mech = _mechanism(trigger_hint=(("vix", "gt", 25.0),))
    assert mech.fingerprint() == _mechanism(
        trigger_hint=(("vix", "gt", 25.0),)).fingerprint()
    assert mech.to_dict()["trigger_hint"] == [["vix", "gt", 25.0]]


def test_scope_validation_and_specificity():
    with pytest.raises(ValueError):
        RepairScope(actions=("HOLD",))
    with pytest.raises(ValueError):
        RepairScope(vix_band=(25.0, 25.0))
    assert RepairScope().specificity() == 0
    scoped = RepairScope(agent_id="a", instruments=("X",),
                         vix_band=(20.0, 30.0))
    assert scoped.specificity() == 3
    assert RepairScope.from_dict(scoped.to_dict()) == scoped


def test_repair_spec_vocab_and_round_trip():
    assert set(APPROVED_RULE_TYPES) == {
        "per_session_order_cap", "exposure_cap", "hold_all"}
    assert "max_quantity" not in APPROVED_RULE_TYPES
    with pytest.raises(ValueError):
        _spec(rule_type="max_quantity")
    spec = _spec()
    assert spec.rule() == {"type": "per_session_order_cap",
                           "max_orders": 1}
    assert RepairSpec.from_dict(spec.to_dict()).fingerprint() == \
        spec.fingerprint()


def test_memory_entry_requires_evidence_and_renders_learned_context():
    from evaluation.context.learned import ContextStatus

    spec = _spec()
    with pytest.raises(ValueError):
        MemoryEntry(entry_id="m", agent_id="a", spec=spec,
                    source_evaluation_id="e", diagnostic_evidence=(),
                    provenance={"p": 1})
    entry = MemoryEntry(
        entry_id="mem-001", agent_id="stub-agent", spec=spec,
        source_evaluation_id="eval-001",
        diagnostic_evidence=("eval-001:pattern",),
        provenance={"candidate_fingerprint": "cfp"},
    )
    clone = MemoryEntry.from_dict(entry.to_dict())
    assert clone.fingerprint() == entry.fingerprint()
    learned = entry.to_learned_context(
        ContextStatus.CANDIDATE,
        validation_result="test-validation",
    )
    assert learned.context_id == "mem-001"
    assert learned.agent_id == "stub-agent"
    assert learned.status is ContextStatus.CANDIDATE
    assert learned.diagnostic_evidence == ("eval-001:pattern",)


def test_candidate_verification_version_audit_records():
    cand = RepairCandidate(candidate_id="cand-001", base_agent_fingerprint="b",
                           spec_fingerprint="s",
                           provenance={"origin": "test"})
    assert cand.fingerprint()
    default = RepairVerification(verification_id="v-001",
                                 candidate_fingerprint="c")
    assert default.verdict == "NSF"
    with pytest.raises(ValueError):
        RepairVerification(verification_id="v", candidate_fingerprint="c",
                           verdict="MAYBE")
    version = RepairVersion(store_sequence=3, rule_table_version="v1")
    assert version.to_dict()["compiler_version"] == "v1"
    first = RepairAuditRecord(seq=1, prev_hash="GENESIS", event="COMPILED",
                              payload={"spec": "s"})
    assert first.event_hash()
    with pytest.raises(TypeError):
        RepairAuditRecord(seq="1", prev_hash="x", event="E", payload={})
