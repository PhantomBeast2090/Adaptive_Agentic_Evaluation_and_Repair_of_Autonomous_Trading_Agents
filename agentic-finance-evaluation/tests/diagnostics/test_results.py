"""Points 4-7: result linkage, non-overwrite, fingerprints, round trip."""

import pytest

from evaluation.diagnostics.contracts.test_results import (
    DiagnosticExecutionStatus,
    DiagnosticTestResult,
)

from .fixtures import make_result, make_state, make_test


def test_result_references_correct_baseline():
    state = make_state()
    from .fixtures import make_hypothesis, make_prediction

    state.register_hypothesis(make_hypothesis())
    state.register_test(make_test())
    state.record_prediction(make_prediction())
    state.record_result(make_result())
    forged = DiagnosticTestResult(
        result_id="R-2",
        test_id="T-1",
        execution_fingerprint="exec-fp-2",
        baseline_evaluation_id="OTHER-BASELINE",
        baseline_fingerprint="baseline-fp-1",
        intervention_fingerprint=make_test().fingerprint(),
        record_fps=("d2",),
        prediction_ids=("P-1",),
        provenance_method="m",
        provenance_version="v",
    )
    with pytest.raises(ValueError):
        state.record_result(forged)
    assert len(state.test_results) == 1


def test_result_cannot_overwrite_baseline():
    result = make_result()
    serialised = result.to_dict()
    blob = str(serialised)
    for forbidden in ("submitted_orders", "executions", "portfolio_before"):
        assert forbidden not in blob
    assert serialised["baseline_evaluation_id"] == "B-1"
    assert serialised["baseline_fingerprint"] == "baseline-fp-1"
    # References only: record and evidence identity travels, payloads don't.
    assert serialised["record_fps"] == ["diag-record-1"]


def test_intervention_fingerprint_sensitivity_and_binding():
    base = make_test()
    altered = make_test(multiplier=10.0)
    assert altered.fingerprint() != base.fingerprint()
    from evaluation.contracts.diagnostic_tests import DiagnosticTest

    relabelled = DiagnosticTest(
        test_id="T-1",
        description="A different experimental intent.",
        target_failure_classes=("excessive_turnover",),
        intervention={"type": "transaction_cost_shift", "multiplier": 5.0},
        measures=("turnover",),
        expected_discrimination="Cost-sensitive turnover collapses.",
        estimated_cost=2.0,
    )
    assert relabelled.fingerprint() != base.fingerprint()
    # A result naming a different intervention than registered is rejected.
    state = make_state()
    from .fixtures import make_hypothesis, make_prediction

    state.register_hypothesis(make_hypothesis())
    state.register_test(base)
    state.record_prediction(make_prediction())
    mismatched = DiagnosticTestResult(
        result_id="R-x",
        test_id="T-1",
        execution_fingerprint="exec-fp-x",
        baseline_evaluation_id="B-1",
        baseline_fingerprint="baseline-fp-1",
        intervention_fingerprint=altered.fingerprint(),
        record_fps=("d9",),
        prediction_ids=("P-1",),
        provenance_method="m",
        provenance_version="v",
    )
    with pytest.raises(ValueError):
        state.record_result(mismatched)


def test_result_validation_and_round_trip():
    with pytest.raises(ValueError):
        make_result(result_id="R-2", status="FAILED")
    failed = make_result(
        result_id="R-2", status="FAILED", error="executor crashed"
    )
    assert failed.outcome == "FAILED"
    assert failed.error == "executor crashed"
    assert (
        DiagnosticExecutionStatus.from_str("INVALID")
        is DiagnosticExecutionStatus.INVALID
    )
    result = make_result()
    assert result.outcome == "COMPLETED"
    assert result.error is None
    restored = DiagnosticTestResult.from_dict(result.to_dict())
    assert restored == result
    assert restored.fingerprint() == result.fingerprint()
    assert restored.measured_by_name("turnover").value == 1.2
    with pytest.raises(KeyError):
        restored.measured_by_name("nope")
