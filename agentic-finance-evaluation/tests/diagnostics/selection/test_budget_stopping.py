"""Budget exhaustion and stopped-state behaviour."""

from evaluation.contracts.budget import EvaluationBudget
from evaluation.contracts.stopping import StoppingReason
from evaluation.diagnostics.selection import select_next_test

from ..fixtures import make_test
from .fixtures import make_rival_state


def _limited_state(max_tests):
    from evaluation.contracts.agent import AgentIdentity
    from evaluation.diagnostics.contracts.diagnostic_state import (
        DiagnosticState,
    )

    base = make_rival_state()
    limited = DiagnosticState(
        diagnostic_id="D-LIM",
        baseline_evaluation_id="B-1",
        baseline_fingerprint="baseline-fp-1",
        agent_identity=AgentIdentity("agent-1", "0.1"),
        environment_spec={"market_fingerprint": "mfp-1"},
        config={},
        budget=EvaluationBudget(None, max_tests, None, None, None),
    )
    for hypothesis in base.hypotheses:
        limited.register_hypothesis(hypothesis)
    for test in base.available_tests:
        limited.register_test(test)
    for prediction in base.predictions:
        limited.record_prediction(prediction)
    return limited


def test_budget_zero_prevents_proposal():
    state = _limited_state(0)
    out = select_next_test(state)
    assert type(out).__name__ == "NoCandidateResult"
    assert out.suggested_stopping == StoppingReason.BUDGET_EXHAUSTED
    assert "budget exhausted" in out.reason
    assert len(state.rationales) == 0
    assert len(state.proposals) == 0


def test_budget_boundary_after_consumption():
    from ..fixtures import make_result, make_test

    state = _limited_state(1)
    out = select_next_test(state)
    assert out.selected_test_id == "T-1"
    state.record_result(make_result(test=make_test(), prediction_ids=("P-1",)))
    refused = select_next_test(state)
    assert type(refused).__name__ == "NoCandidateResult"
    assert refused.suggested_stopping == StoppingReason.BUDGET_EXHAUSTED


def test_proposal_does_not_consume_budget():
    state = _limited_state(5)
    before = state.budget_usage()
    select_next_test(state)
    assert state.budget_usage() == before
    assert state.tests_consumed() == 0


def test_stopped_state_records_nothing():
    state = make_rival_state()
    state.set_stopping_reason(StoppingReason.HYPOTHESIS_UNRESOLVED)
    out = select_next_test(state)
    assert type(out).__name__ == "NoCandidateResult"
    assert out.suggested_stopping == StoppingReason.HYPOTHESIS_UNRESOLVED
    assert "already stopped" in out.reason
    assert len(state.rationales) == 0
    assert len(state.proposals) == 0
