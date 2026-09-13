"""D. Hypothesis contract tests."""

import pytest

from evaluation.contracts.hypotheses import Hypothesis, HypothesisStatus


def _hypothesis_kwargs(**overrides):
    kwargs = {
        "hypothesis_id": "H-017",
        "failure_class": "excessive_turnover",
        "mechanism": "Agent reacts excessively to short-lived price movements.",
        "evidence_refs": ("E-102", "E-113"),
        "confidence": 0.68,
        "alternative_hypotheses": ("transaction-cost insensitivity",),
        "discriminating_tests": ("T-cost-shift",),
        "status": HypothesisStatus.PROPOSED,
    }
    kwargs.update(overrides)
    return kwargs


def test_valid_hypothesis():
    hypothesis = Hypothesis(**_hypothesis_kwargs())
    assert hypothesis.status is HypothesisStatus.PROPOSED
    assert hypothesis.fingerprint()


def test_invalid_hypothesis_rejected():
    with pytest.raises(ValueError):
        # Symptom restated as mechanism: failure is not proven mechanism.
        Hypothesis(
            **_hypothesis_kwargs(mechanism="excessive_turnover")
        )
    with pytest.raises(ValueError):
        Hypothesis(**_hypothesis_kwargs(confidence=1.5))
    with pytest.raises(ValueError):
        # A status claim without grounding evidence.
        Hypothesis(
            **_hypothesis_kwargs(
                evidence_refs=(), status=HypothesisStatus.SUPPORTED
            )
        )
    with pytest.raises(ValueError):
        Hypothesis(**_hypothesis_kwargs(status="PROVEN"))


def test_competing_hypotheses_share_evidence():
    first = Hypothesis(**_hypothesis_kwargs(hypothesis_id="H-017"))
    second = Hypothesis(
        **_hypothesis_kwargs(
            hypothesis_id="H-018",
            mechanism="Agent sizes positions unstably under volatility.",
            alternative_hypotheses=("short-horizon overreaction",),
        )
    )
    assert first.evidence_refs == second.evidence_refs
    assert first.mechanism != second.mechanism
    assert first.fingerprint() != second.fingerprint()


def test_status_transitions_are_pure():
    hypothesis = Hypothesis(**_hypothesis_kwargs())
    weakened = hypothesis.with_status(HypothesisStatus.WEAKENED)
    assert hypothesis.status is HypothesisStatus.PROPOSED
    assert weakened.status is HypothesisStatus.WEAKENED
    assert weakened.fingerprint() != hypothesis.fingerprint()
    with pytest.raises(ValueError):
        hypothesis.with_status("PROVEN")


def test_deterministic_serialization_round_trip():
    hypothesis = Hypothesis(
        **_hypothesis_kwargs(status=HypothesisStatus.SUPPORTED)
    )
    restored = Hypothesis.from_dict(hypothesis.to_dict())
    assert restored == hypothesis
    assert restored.fingerprint() == hypothesis.fingerprint()
