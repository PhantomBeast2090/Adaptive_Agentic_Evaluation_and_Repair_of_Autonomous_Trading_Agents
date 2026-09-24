"""E4-A contract tests: LearnedContext determinism and lifecycle."""

import pytest

from evaluation.context.learned import ContextStatus, LearnedContext


def _candidate(**overrides):
    params = {
        "context_id": "ctx-abc123",
        "agent_id": "churn-stub@0.1",
        "source_evaluation_id": "B-R",
        "failure_mechanism": "turnover",
        "observed_pattern": "turnover DECREASE on candidate_diagnostic",
        "triggering_conditions": ("candidate_diagnostic",),
        "diagnostic_evidence": ("E-1",),
        "corrective_principle": "DECREASE turnover via rule-table v1",
        "applicability_conditions": ("candidate_diagnostic",),
        "contraindications": (),
        "expected_effect": "turnover strictly decreases",
        "validation_result": "ACCEPTED",
        "validation_metrics": {"turnover": {"delta": -1.0}},
        "held_out_evidence": {"candidate_heldout": {"turnover": 0.5}},
        "provenance": {"proposal_fingerprint": "p"},
        "status": ContextStatus.CANDIDATE,
        "version": "v1",
    }
    params.update(overrides)
    return LearnedContext(**params)


def test_deterministic_serialisation_and_fingerprint_stability():
    first, second = _candidate(), _candidate()
    assert first.to_dict() == second.to_dict()
    assert first.fingerprint() == second.fingerprint()
    assert len(first.fingerprint()) == 64


def test_round_trip_serialisation():
    candidate = _candidate()
    assert LearnedContext.from_dict(candidate.to_dict()) == candidate


def test_unknown_field_rejection():
    with pytest.raises(ValueError):
        LearnedContext.from_dict(
            {**_candidate().to_dict(), "zzz": 1}
        )
    with pytest.raises(ValueError):
        ContextStatus.from_str("MAYBE")


def test_malformed_data_rejection():
    with pytest.raises(ValueError):
        _candidate(context_id="  ")
    with pytest.raises(ValueError):
        _candidate(diagnostic_evidence=())
    with pytest.raises(ValueError):
        _candidate(provenance={})
    with pytest.raises(TypeError):
        _candidate(validation_metrics=[1, 2])
    with pytest.raises(ValueError):
        LearnedContext.from_dict({"context_id": "x"})


def test_version_handling():
    assert _candidate().version == "v1"
    assert _candidate(version="v2").version == "v2"
    assert _candidate(version="v2").fingerprint() != _candidate().fingerprint()


def test_provenance_preservation():
    candidate = _candidate()
    revived = LearnedContext.from_dict(candidate.to_dict())
    assert revived.provenance == {"proposal_fingerprint": "p"}
    assert revived.diagnostic_evidence == ("E-1",)


def test_status_constraints():
    candidate = _candidate()
    validated = candidate.with_status(ContextStatus.VALIDATED)
    assert validated.status is ContextStatus.VALIDATED
    assert candidate.status is ContextStatus.CANDIDATE
    admitted = validated.with_status("ADMITTED")
    assert admitted.status is ContextStatus.ADMITTED
    # Diagnosed candidates cannot masquerade as validated knowledge.
    with pytest.raises(ValueError):
        candidate.with_status(ContextStatus.ADMITTED)
    with pytest.raises(ValueError):
        candidate.with_status(ContextStatus.VALIDATED).with_status(
            ContextStatus.CANDIDATE
        )
    with pytest.raises(ValueError):
        admitted.with_status(ContextStatus.REJECTED)
    rejected = candidate.with_status(ContextStatus.REJECTED)
    with pytest.raises(ValueError):
        rejected.with_status(ContextStatus.VALIDATED)
    quarantined = candidate.with_status(ContextStatus.QUARANTINED)
    assert quarantined.with_status("VALIDATED").status is (
        ContextStatus.VALIDATED
    )
    assert admitted.with_status("SUPERSEDED").status is (
        ContextStatus.SUPERSEDED
    )
