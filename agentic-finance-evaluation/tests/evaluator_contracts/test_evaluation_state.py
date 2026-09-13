"""F. EvaluationState tests."""

import pytest

from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.budget import EvaluationBudget
from evaluation.contracts.diagnostic_tests import DiagnosticTest
from evaluation.contracts.evaluation_state import EvaluationState
from evaluation.contracts.evidence import BehavioralEvidence, EvidenceCategory
from evaluation.contracts.hypotheses import Hypothesis, HypothesisStatus
from evaluation.contracts.stopping import StoppingReason


def _budget():
    return EvaluationBudget(
        max_episodes=10,
        max_tests=5,
        max_repairs=2,
        max_validation_runs=2,
        max_runtime=3600,
    )


def _state(**overrides):
    kwargs = {
        "evaluation_id": "EV-001",
        "agent_identity": AgentIdentity("test-agent", "0.1"),
        "environment_spec": {
            "market_fingerprint": "mfp-001",
            "grid_start": "2023-05-15",
            "grid_end": "2023-05-26",
        },
        "config": {"strict_pit": True},
        "budget": _budget(),
    }
    kwargs.update(overrides)
    return EvaluationState(**kwargs)


def _evidence(evidence_id="E-001"):
    return BehavioralEvidence(
        evidence_id=evidence_id,
        category=EvidenceCategory.RISK,
        metric_name="turnover",
        value=3.2,
        decision_refs=("state-fp-001",),
        derivation={"method": "unit_test"},
    )


def _hypothesis():
    return Hypothesis(
        hypothesis_id="H-001",
        failure_class="excessive_turnover",
        mechanism="Agent overreacts to short-lived moves.",
        evidence_refs=("E-001",),
        confidence=0.5,
    )


def _test():
    return DiagnosticTest(
        test_id="T-001",
        description="Shift costs and replay.",
        target_failure_classes=("excessive_turnover",),
        intervention={"type": "transaction_cost_shift"},
        measures=("turnover",),
        expected_discrimination="Turnover collapses iff cost-sensitive.",
        estimated_cost=1.0,
    )


def test_valid_construction():
    state = _state()
    assert state.evidence == ()
    assert state.stopping_reason is None
    assert state.fingerprint()


def test_accumulation_and_duplicate_identity_rejected():
    state = _state()
    state.add_baseline_evidence(_evidence("E-000"))
    state.add_evidence(_evidence("E-001"))
    state.add_hypothesis(_hypothesis())
    state.record_test(_test())
    state.record_test_result("T-001", {"outcome": "completed"})
    assert len(state.baseline_evidence) == 1
    assert len(state.evidence) == 1
    with pytest.raises(ValueError):
        state.add_evidence(_evidence("E-001"))
    with pytest.raises(ValueError):
        state.add_hypothesis(_hypothesis())
    with pytest.raises(ValueError):
        state.record_test(_test())


def test_orphan_test_result_rejected():
    state = _state()
    with pytest.raises(ValueError):
        state.record_test_result("T-unknown", {"outcome": "completed"})
    with pytest.raises(ValueError):
        state.record_test_result("T-001", {"no_outcome": True})


def test_serialization_round_trip_equality():
    state = _state()
    state.add_evidence(_evidence())
    state.add_hypothesis(_hypothesis())
    state.record_test(_test())
    state.record_test_result("T-001", {"outcome": "completed"})
    state.note_repair_candidate({"candidate_id": "R-001"})
    state.note_validation_result({"candidate_id": "R-001", "passed": True})
    state.note_regression({"description": "none observed"})
    state.set_stopping_reason(StoppingReason.BUDGET_EXHAUSTED)
    restored = EvaluationState.from_dict(state.to_dict())
    assert restored == state
    assert restored.fingerprint() == state.fingerprint()


def test_deterministic_fingerprint():
    assert _state().fingerprint() == _state().fingerprint()
    state = _state()
    state.add_evidence(_evidence())
    assert state.fingerprint() != _state().fingerprint()


def test_stopping_reason_set_once():
    state = _state()
    state.set_stopping_reason("BUDGET_EXHAUSTED")
    assert state.stopping_reason is StoppingReason.BUDGET_EXHAUSTED
    state.set_stopping_reason(StoppingReason.BUDGET_EXHAUSTED)  # idempotent
    with pytest.raises(ValueError):
        state.set_stopping_reason(StoppingReason.SUCCESS_CONFIDENT)
