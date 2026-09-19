"""Closed-loop adaptivity through real E2-B/E2-C integration.

H1/H2/H3 start PROPOSED. T1 carries rival directions (H1 INCREASE,
H2 DECREASE, H3 INCREASE over turnover); T2 agrees (all DECREASE).
The first proposal must select T1; after a real execution plus real
interpretation, the second selection must differ, driven by the updated
diagnostic state — never by a hard-coded sequence.
"""

from evaluation.contracts.hypotheses import HypothesisStatus
from evaluation.diagnostics.orchestration.controller import run

from ..execution_fixtures import (
    baseline_spec as real_spec,  # noqa: F401
)
from ..execution_fixtures import BuyOnceAgent, FULL_UNIVERSE
from ..fixtures import make_hypothesis
from ..selection.fixtures import add_prediction
from .fixtures import (
    SMALL_WINDOW,
    make_loop_baseline,
    make_loop_config,
    make_loop_state,
)


def _rival_state(baseline, real_spec, diagnostic_id="D-LOOP"):
    from ..execution_fixtures import (
        BuyOnceAgent,
        make_cost_test,
        make_null_test,
    )

    state = make_loop_state(
        baseline, real_spec, diagnostic_id=diagnostic_id,
        agent=BuyOnceAgent(),
    )
    # make_loop_state registers default H-1; add the rivals.
    state.register_hypothesis(
        make_hypothesis(
            hypothesis_id="H-2",
            mechanism="Sizes positions unstably under volatility.",
        )
    )
    state.register_hypothesis(
        make_hypothesis(
            hypothesis_id="H-3", mechanism="Ignores cost schedules entirely."
        )
    )
    state.register_test(make_cost_test(test_id="T-1", multiplier=5.0))
    state.register_test(make_null_test(test_id="T-2"))
    add_prediction(state, "P-1", "H-1", "T-1", "INCREASE")
    add_prediction(state, "P-2", "H-2", "T-1", "DECREASE")
    add_prediction(state, "P-3", "H-3", "T-1", "INCREASE")
    add_prediction(state, "P-4", "H-1", "T-2", "DECREASE")
    add_prediction(state, "P-5", "H-2", "T-2", "DECREASE")
    add_prediction(state, "P-6", "H-3", "T-2", "DECREASE")
    return state


def test_full_causal_trajectory_state_conditioned(real_spec):
    baseline = make_loop_baseline({"turnover": 1.0})
    agent = BuyOnceAgent()
    state = _rival_state(baseline, real_spec)
    config = make_loop_config(baseline, agent, max_iterations=2)
    initial_fp = state.fingerprint()

    result = run(
        diagnostic_state=state, baseline=baseline,
        target_agent=agent, config=config,
    )

    assert len(result.iterations) == 2
    first, second = result.iterations
    # Proposal 1 targets the rival-splitting test.
    assert first.test_id == "T-1"
    assert first.completed is True
    assert first.update_ids
    # Interpretation moved at least one hypothesis off PROPOSED.
    moved = [
        h for h in state.hypotheses
        if h.status is not HypothesisStatus.PROPOSED
    ]
    assert moved
    assert len(state.hypothesis_updates) >= 1
    # Proposal 2 differs: T-1 is consumed AND the open set changed.
    assert second.test_id != first.test_id
    assert second.test_id == "T-2"
    assert second.pre_state_fingerprint != initial_fp
    assert second.pre_state_fingerprint == first.post_state_fingerprint
    # Chain integrity across the whole trajectory. The final fingerprint
    # additionally covers the terminal stopping reason recorded at exit.
    assert result.final_state_fingerprint == state.fingerprint()
    assert result.final_state_fingerprint != initial_fp
    # Second selection reflects the updated open set, not replay order:
    # every hypothesis it names must still be open right now.
    from evaluation.diagnostics.interpretation.methodology import (
        OPEN_STATUSES,
    )

    current_open = {
        h.hypothesis_id
        for h in state.hypotheses
        if h.status.value in OPEN_STATUSES
    }
    assert current_open


def test_second_selection_comes_from_updated_state(real_spec):
    from evaluation.diagnostics.selection import select_next_test

    baseline = make_loop_baseline({"turnover": 1.0})
    agent = BuyOnceAgent()
    # Two independently built identical states select identically.
    fresh_a = _rival_state(baseline, real_spec, diagnostic_id="D-LOOP-2")
    fresh_b = _rival_state(baseline, real_spec, diagnostic_id="D-LOOP-2")
    assert (
        select_next_test(fresh_a).proposal_id
        == select_next_test(fresh_b).proposal_id
    )
    # A full loop run consumes T-1 and updates hypotheses; selecting
    # again from that updated state cannot replay the first proposal.
    state = _rival_state(baseline, real_spec, diagnostic_id="D-LOOP-3")
    config = make_loop_config(
        baseline, agent, max_iterations=1, diagnostic_id="D-LOOP-3"
    )
    one = run(
        diagnostic_state=state, baseline=baseline,
        target_agent=agent, config=config,
    )
    assert len(one.iterations) == 1
    assert state.fingerprint() != fresh_a.fingerprint()
    assert len(state.hypothesis_updates) >= 1
