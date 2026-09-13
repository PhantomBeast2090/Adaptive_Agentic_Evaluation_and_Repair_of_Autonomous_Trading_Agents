"""C. BehavioralEvidence tests."""

import pytest

from evaluation.contracts.decision_record import DecisionRecord
from evaluation.contracts.evidence import BehavioralEvidence, EvidenceCategory


def _evidence_kwargs(**overrides):
    kwargs = {
        "evidence_id": "E-001",
        "category": EvidenceCategory.TEMPORAL,
        "metric_name": "reaction_latency_sessions",
        "value": 2.0,
        "decision_refs": ("state-fp-001", "state-fp-002"),
        "derivation": {"method": "unit_test", "producer_version": "e0"},
        "severity": "medium",
        "confidence": 0.6,
        "provenance": {"market_fingerprint": "mfp-001"},
    }
    kwargs.update(overrides)
    return kwargs


def test_valid_evidence():
    evidence = BehavioralEvidence(**_evidence_kwargs())
    assert evidence.category is EvidenceCategory.TEMPORAL
    assert evidence.fingerprint()


def test_invalid_evidence_rejected():
    with pytest.raises(ValueError):
        BehavioralEvidence(**_evidence_kwargs(category="NOT_A_CATEGORY"))
    with pytest.raises(ValueError):
        # Undefined metric without a reason is silent fabrication.
        BehavioralEvidence(**_evidence_kwargs(value=None))
    with pytest.raises(ValueError):
        # Reason alongside a present value is contradictory.
        BehavioralEvidence(
            **_evidence_kwargs(value=1.0, value_absent_reason="n/a")
        )
    with pytest.raises(ValueError):
        BehavioralEvidence(**_evidence_kwargs(decision_refs=()))
    with pytest.raises(ValueError):
        BehavioralEvidence(**_evidence_kwargs(derivation={}))


def test_category_validation_and_coercion():
    evidence = BehavioralEvidence(**_evidence_kwargs(category="RISK"))
    assert evidence.category is EvidenceCategory.RISK
    assert BehavioralEvidence.from_dict(evidence.to_dict()) == evidence
    for member in EvidenceCategory:
        assert EvidenceCategory.from_str(member.value) is member
    with pytest.raises(ValueError):
        EvidenceCategory.from_str("risk")


def test_raw_vs_derived_separation():
    # A DecisionRecord is a raw event; it is never valid derived evidence
    # and carries no evidence identity.
    assert not hasattr(DecisionRecord, "evidence_id")
    assert not hasattr(DecisionRecord, "category")
    evidence = BehavioralEvidence(**_evidence_kwargs())
    assert not hasattr(evidence, "submitted_orders")
    assert not hasattr(evidence, "executions")
    # Evidence references raw records by fingerprint, not by containment.
    assert evidence.decision_refs == ("state-fp-001", "state-fp-002")
    undefined = BehavioralEvidence(
        **_evidence_kwargs(
            evidence_id="E-002", value=None,
            value_absent_reason="no eligible sessions in window",
        )
    )
    assert undefined.value is None
    assert undefined.fingerprint() != evidence.fingerprint()


def test_nested_derived_metadata_is_immutable():
    evidence = BehavioralEvidence(**_evidence_kwargs(
        derivation={"method": "unit_test", "parameters": {"window": 5}}
    ))
    with pytest.raises(TypeError):
        evidence.derivation["parameters"]["window"] = 10
