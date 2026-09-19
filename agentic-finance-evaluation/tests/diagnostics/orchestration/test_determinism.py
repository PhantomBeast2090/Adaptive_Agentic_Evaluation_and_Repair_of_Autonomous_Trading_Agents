"""Deterministic replay: two independent identical runs coincide."""

from evaluation.diagnostics.orchestration.controller import run

from ..execution_fixtures import (
    baseline_spec as real_spec,  # noqa: F401
)
from ..execution_fixtures import HoldAgent, make_null_test
from ..selection.fixtures import add_prediction
from .fixtures import make_loop_baseline, make_loop_config, make_loop_state


def _run_once(baseline, real_spec, diagnostic_id, seed):
    agent = HoldAgent()
    state = make_loop_state(
        baseline, real_spec, diagnostic_id=diagnostic_id, agent=agent
    )
    state.register_test(make_null_test(test_id="T-1"))
    add_prediction(state, "P-1", "H-1", "T-1", "INCREASE")
    config = make_loop_config(
        baseline, agent, max_iterations=1,
        diagnostic_id=diagnostic_id, seed=seed,
    )
    return run(
        diagnostic_state=state, baseline=baseline,
        target_agent=agent, config=config,
    ), state


def test_replay_produces_identical_trace(real_spec):
    baseline = make_loop_baseline()
    first, first_state = _run_once(baseline, real_spec, "D-REP", seed=11)
    second, second_state = _run_once(baseline, real_spec, "D-REP", seed=11)
    assert first.to_dict() == second.to_dict()
    assert first.fingerprint() == second.fingerprint()
    assert [e.test_id for e in first.iterations] == ["T-1"]
    assert [e.test_id for e in second.iterations] == ["T-1"]


def test_replay_matches_on_all_identity_fields(real_spec):
    baseline = make_loop_baseline()
    first, first_state = _run_once(baseline, real_spec, "D-REP2", seed=11)
    second, second_state = _run_once(baseline, real_spec, "D-REP2", seed=11)
    first_entry, second_entry = first.iterations[0], second.iterations[0]
    assert first_entry.proposal_id == second_entry.proposal_id
    assert first_entry.execution_fingerprint == (
        second_entry.execution_fingerprint
    )
    assert first_entry.interpretation_id == second_entry.interpretation_id
    assert first_entry.update_ids == second_entry.update_ids
    assert first.terminal_condition == second.terminal_condition
    assert first.stopping_reason == second.stopping_reason
    assert first.final_state_fingerprint == (
        second.final_state_fingerprint
    )
    assert first.final_state_fingerprint == first_state.fingerprint()
    assert second.final_state_fingerprint == second_state.fingerprint()


def test_seed_change_alters_execution_identity(real_spec):
    baseline = make_loop_baseline()
    first, _ = _run_once(baseline, real_spec, "D-SEED", seed=11)
    second, _ = _run_once(baseline, real_spec, "D-SEED", seed=12)
    assert first.iterations[0].execution_fingerprint != (
        second.iterations[0].execution_fingerprint
    )
    assert first.fingerprint() != second.fingerprint()
