"""Points 10-12 + round trip + budget + E0 mirror: DiagnosticState."""

import pytest

from evaluation.contracts.stopping import StoppingReason
from evaluation.diagnostics.contracts.diagnostic_state import (
    DiagnosticState,
    UncertaintySnapshot,
)

from .fixtures import (
    make_full_state,
    make_hypothesis,
    make_prediction,
    make_result,
    make_state,
    make_test,
    make_update,
)


def test_rejects_orphan_results_and_duplicates():
    state = make_state()
    with pytest.raises(ValueError):
        state.record_result(make_result())
    state.register_test(make_test())
    with pytest.raises(ValueError):
        state.record_result(make_result())
    state.register_hypothesis(make_hypothesis())
    state.record_prediction(make_prediction())
    state.record_result(make_result())
    with pytest.raises(ValueError):
        state.record_result(make_result())
    with pytest.raises(ValueError):
        state.register_test(make_test())
    with pytest.raises(ValueError):
        state.register_hypothesis(make_hypothesis())
    with pytest.raises(KeyError):
        state.hypothesis("H-unknown")


def test_uncertainty_snapshot_validation_and_replacement():
    state = make_state()
    state.register_hypothesis(make_hypothesis())
    snapshot = UncertaintySnapshot(
        assessment_id="UA-1",
        method="manual-fixture",
        version="v1",
        open_hypothesis_ids=("H-1",),
        summary="One open hypothesis.",
    )
    state.record_uncertainty(snapshot)
    assert state.uncertainty == snapshot
    with pytest.raises(ValueError):
        state.record_uncertainty(
            UncertaintySnapshot(
                assessment_id="UA-2",
                method="m",
                version="v",
                open_hypothesis_ids=("H-ghost",),
                summary="Unknown hypothesis.",
            )
        )
    replacement = UncertaintySnapshot(
        assessment_id="UA-3",
        method="manual-fixture",
        version="v1",
        open_hypothesis_ids=(),
        summary="Nothing open.",
    )
    state.record_uncertainty(replacement)
    assert state.uncertainty.assessment_id == "UA-3"


def test_serialisation_round_trip_and_e0_mirror():
    state = make_full_state()
    restored = DiagnosticState.from_dict(state.to_dict())
    assert restored == state
    assert restored.fingerprint() == state.fingerprint()
    mirror = state.evaluation_state
    assert {t.test_id for t in mirror.executed_tests} == {"T-1", "T-2"}
    assert len(mirror.test_results) == 1
    assert {h.hypothesis_id for h in mirror.hypotheses} == {"H-1", "H-2"}
    with pytest.raises(ValueError):
        DiagnosticState.from_dict(
            {**state.to_dict(), "unknown_field": 1}
        )


def test_budget_usage_and_stopping():
    state = make_full_state()
    assert state.tests_consumed() == 1
    assert state.budget_usage() == {"tests": 1}
    assert state.budget_exhausted() is False
    state.set_stopping_reason(StoppingReason.HYPOTHESIS_UNRESOLVED)
    assert state.stopping_reason is StoppingReason.HYPOTHESIS_UNRESOLVED
    assert (
        state.evaluation_state.stopping_reason
        is StoppingReason.HYPOTHESIS_UNRESOLVED
    )
    with pytest.raises(ValueError):
        state.set_stopping_reason(StoppingReason.BUDGET_EXHAUSTED)
    with pytest.raises(ValueError):
        state.set_stopping_reason("NOT_A_REASON")


def test_budget_exhaustion_boundary():
    from evaluation.contracts.agent import AgentIdentity
    from evaluation.contracts.budget import EvaluationBudget

    tight = DiagnosticState(
        diagnostic_id="D-tight",
        baseline_evaluation_id="B-1",
        baseline_fingerprint="baseline-fp-1",
        agent_identity=AgentIdentity("a", "1"),
        environment_spec={"market_fingerprint": "mfp"},
        config={},
        budget=EvaluationBudget(None, 1, None, None, None),
    )
    assert tight.budget_exhausted() is False
    tight.register_hypothesis(make_hypothesis())
    tight.register_test(make_test())
    tight.record_prediction(make_prediction())
    tight.record_result(make_result())
    assert tight.budget_exhausted() is True
