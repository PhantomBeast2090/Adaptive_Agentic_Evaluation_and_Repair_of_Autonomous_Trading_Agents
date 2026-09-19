"""Budget semantics: single-execution bound, no overrun, no consumption."""

from evaluation.diagnostics.orchestration.controller import run

from ..execution_fixtures import (
    baseline_spec as real_spec,  # noqa: F401
)
from ..execution_fixtures import HoldAgent, make_null_test
from ..selection.fixtures import add_prediction
from .fixtures import make_loop_baseline, make_loop_config, make_loop_state


def _single_test_state(baseline, real_spec, diagnostic_id="D-BUD", max_tests=1):
    state = make_loop_state(
        baseline, real_spec, diagnostic_id=diagnostic_id, max_tests=max_tests
    )
    state.register_test(make_null_test(test_id="T-1"))
    add_prediction(state, "P-1", "H-1", "T-1", "INCREASE")
    return state


def test_only_one_execution_permitted(real_spec):
    baseline = make_loop_baseline()
    agent = HoldAgent()
    state = _single_test_state(baseline, real_spec)
    config = make_loop_config(
        baseline, agent, max_iterations=5, diagnostic_id="D-BUD"
    )
    result = run(
        diagnostic_state=state, baseline=baseline,
        target_agent=agent, config=config,
    )
    assert len(result.iterations) == 1
    assert result.iterations[0].completed is True
    assert state.tests_consumed() == 1
    # Budget now exhausted: termination is explicit, not a silent stop.
    assert result.terminal_condition == "no_candidate"
    from evaluation.contracts.stopping import StoppingReason

    assert result.stopping_reason is StoppingReason.BUDGET_EXHAUSTED
    assert result.no_candidate_reason is not None


def test_max_iterations_distinct_from_test_budget(real_spec):
    baseline = make_loop_baseline()
    agent = HoldAgent()
    state = _single_test_state(
        baseline, real_spec, diagnostic_id="D-BUD2", max_tests=10
    )
    config = make_loop_config(
        baseline, agent, max_iterations=1, diagnostic_id="D-BUD2"
    )
    result = run(
        diagnostic_state=state, baseline=baseline,
        target_agent=agent, config=config,
    )
    # Iteration cap hit after one completed iteration, budget unexhausted.
    assert result.terminal_condition == "iteration_cap"
    assert state.tests_consumed() == 1
    assert state.budget_exhausted() is False


def test_proposal_formation_consumes_nothing(real_spec):
    from evaluation.diagnostics.selection import select_next_test

    baseline = make_loop_baseline()
    state = _single_test_state(baseline, real_spec, diagnostic_id="D-BUD3")
    before = state.tests_consumed()
    select_next_test(state)
    assert state.tests_consumed() == before
