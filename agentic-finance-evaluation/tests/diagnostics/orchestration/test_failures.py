"""FAILED/INVALID failure semantics: visible, distinguished, explicit."""

from evaluation.contracts.stopping import StoppingReason
from evaluation.diagnostics.orchestration.controller import run

from ..execution_fixtures import (
    baseline_spec as real_spec,  # noqa: F401
)
from ..execution_fixtures import ExplodingAgent, HoldAgent, make_null_test
from ..selection.fixtures import add_prediction
from .fixtures import make_loop_baseline, make_loop_config, make_loop_state
from .test_budget import _single_test_state


def test_failed_execution_stays_visible_and_loop_continues(real_spec):
    baseline = make_loop_baseline()
    agent = ExplodingAgent()
    state = make_loop_state(
        baseline, real_spec, diagnostic_id="D-FAIL", max_tests=10,
        agent=agent,
    )
    state.register_test(make_null_test(test_id="T-1"))
    state.register_test(make_null_test(test_id="T-2"))
    add_prediction(state, "P-1", "H-1", "T-1", "INCREASE")
    add_prediction(state, "P-2", "H-1", "T-2", "INCREASE")
    config = make_loop_config(
        baseline, agent, max_iterations=3, diagnostic_id="D-FAIL"
    )
    result = run(
        diagnostic_state=state, baseline=baseline,
        target_agent=agent, config=config,
    )
    failed = [entry for entry in result.iterations if not entry.completed]
    assert failed
    first_failed = failed[0]
    assert first_failed.interpretation_id is None
    assert first_failed.update_ids == ()
    assert first_failed.uncertainty_id is None
    # FAILED is never represented as COMPLETED.
    assert all(
        entry.completed or entry.interpretation_id is None
        for entry in result.iterations
    )
    assert len(state.test_results) == len(result.iterations)


def test_invalid_result_never_interpreted_as_completed(real_spec):
    from evaluation.contracts.diagnostic_tests import DiagnosticTest

    baseline = make_loop_baseline()
    agent = HoldAgent()
    state = make_loop_state(
        baseline, real_spec, diagnostic_id="D-INV", max_tests=10
    )
    state.register_test(
        DiagnosticTest(
            test_id="T-BOGUS",
            description="Requests an unknown measure.",
            target_failure_classes=("excessive_turnover",),
            intervention={"type": "null_intervention"},
            measures=("not_a_real_metric",),
            expected_discrimination="Nothing honest.",
            estimated_cost=1.0,
        )
    )
    add_prediction(state, "P-1", "H-1", "T-BOGUS", "INCREASE")
    config = make_loop_config(
        baseline, agent, max_iterations=2, diagnostic_id="D-INV"
    )
    result = run(
        diagnostic_state=state, baseline=baseline,
        target_agent=agent, config=config,
    )
    assert len(result.iterations) == 1
    assert result.iterations[0].completed is False
    assert result.iterations[0].interpretation_id is None
    assert len(state.hypothesis_updates) == 0
    assert result.terminal_condition == "no_candidate"


def test_failure_policy_is_explicit_not_silent(real_spec):
    baseline = make_loop_baseline()
    agent = HoldAgent()
    state = _single_test_state(baseline, real_spec, diagnostic_id="D-POL")
    assert state.tests_consumed() == 0
    config = make_loop_config(
        baseline, agent, max_iterations=5, diagnostic_id="D-POL"
    )
    result = run(
        diagnostic_state=state, baseline=baseline,
        target_agent=agent, config=config,
    )
    assert result.stopping_reason is StoppingReason.BUDGET_EXHAUSTED
    assert result.no_candidate_reason is not None
    assert len(result.iterations) == 1
