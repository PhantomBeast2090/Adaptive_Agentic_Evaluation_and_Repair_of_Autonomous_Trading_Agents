"""Stopping mapping and already-stopped defences."""

from evaluation.contracts.stopping import StoppingReason
from evaluation.diagnostics.orchestration.controller import run
from evaluation.diagnostics.orchestration.stopping import TERMINAL_MAPPING

from ..execution_fixtures import (
    baseline_spec as real_spec,  # noqa: F401
)
from ..execution_fixtures import HoldAgent
from .fixtures import make_loop_baseline, make_loop_config, make_loop_state


def test_iteration_cap_maps_to_unresolved(real_spec):
    baseline = make_loop_baseline()
    agent = HoldAgent()
    state = make_loop_state(baseline, real_spec)
    from ..execution_fixtures import make_null_test
    from ..selection.fixtures import add_prediction

    state.register_test(make_null_test(test_id="T-1"))
    add_prediction(state, "P-1", "H-1", "T-1", "INCREASE")
    config = make_loop_config(baseline, agent, max_iterations=1)
    result = run(
        diagnostic_state=state, baseline=baseline,
        target_agent=agent, config=config,
    )
    assert result.terminal_condition == "iteration_cap"
    assert result.stopping_reason is StoppingReason.HYPOTHESIS_UNRESOLVED
    assert state.stopping_reason is StoppingReason.HYPOTHESIS_UNRESOLVED
    assert len(result.iterations) == 1


def test_terminal_mapping_table():
    assert TERMINAL_MAPPING["iteration_cap"] is (
        StoppingReason.HYPOTHESIS_UNRESOLVED
    )
    assert TERMINAL_MAPPING["budget_exhausted"] is (
        StoppingReason.BUDGET_EXHAUSTED
    )
    assert TERMINAL_MAPPING["no_actionable"] is (
        StoppingReason.NO_ACTIONABLE_FAILURE
    )
    assert TERMINAL_MAPPING["unresolved"] is (
        StoppingReason.HYPOTHESIS_UNRESOLVED
    )
    assert StoppingReason.SUCCESS_CONFIDENT not in set(
        TERMINAL_MAPPING.values()
    )


def test_no_candidate_suggestion_honoured(real_spec):
    baseline = make_loop_baseline()
    agent = HoldAgent()
    state = make_loop_state(baseline, real_spec, max_tests=0)
    config = make_loop_config(baseline, agent)
    result = run(
        diagnostic_state=state, baseline=baseline,
        target_agent=agent, config=config,
    )
    assert result.terminal_condition == "no_candidate"
    assert result.stopping_reason is StoppingReason.BUDGET_EXHAUSTED
    assert result.iterations == ()
    assert "budget" in result.no_candidate_reason.lower()
