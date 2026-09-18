"""Discrimination (D) and coverage (C) calculation."""

from evaluation.diagnostics.selection.candidates import candidate_statistics

from ..fixtures import make_state
from .fixtures import make_rival_state, make_three_way_state


def _stats_by_id(state, test_id):
    test = next(t for t in state.available_tests if t.test_id == test_id)
    return candidate_statistics(state, test)


def test_opposing_pair_gives_discrimination_one():
    state = make_rival_state()
    stats = _stats_by_id(state, "T-1")
    assert stats.discrimination_pairs == 1
    assert stats.open_coverage == 2
    assert stats.estimated_cost == 2.0


def test_three_hypotheses_two_directional_groups():
    # H-1 DECREASE vs H-2/H-3 INCREASE: pairs (H-1,H-2),(H-1,H-3) differ.
    state = make_three_way_state()
    stats_a = _stats_by_id(state, "T-A")
    assert stats_a.discrimination_pairs == 2
    assert stats_a.open_coverage == 3
    stats_b = _stats_by_id(state, "T-B")
    assert stats_b.discrimination_pairs == 0
    assert stats_b.open_coverage == 3


def test_identical_directions_give_zero_discrimination():
    state = make_state()
    from ..fixtures import make_hypothesis, make_rival, make_test

    state.register_hypothesis(make_hypothesis())
    state.register_hypothesis(make_rival())
    state.register_test(make_test())
    from .fixtures import add_prediction

    add_prediction(state, "P-1", "H-1", "T-1", "INCREASE")
    add_prediction(state, "P-2", "H-2", "T-1", "INCREASE")
    stats = _stats_by_id(state, "T-1")
    assert stats.discrimination_pairs == 0
    assert stats.open_coverage == 2


def test_coverage_counts_distinct_open_hypotheses():
    from ..fixtures import make_hypothesis, make_state, make_test
    from .fixtures import add_prediction

    state = make_state()
    state.register_hypothesis(make_hypothesis())
    state.register_test(make_test())
    add_prediction(state, "P-1", "H-1", "T-1", "DECREASE")
    stats = _stats_by_id(state, "T-1")
    assert stats.open_coverage == 1
    assert stats.discrimination_pairs == 0


def test_statistics_carry_no_hypothesis_ranking():
    state = make_three_way_state()
    stats = _stats_by_id(state, "T-A")
    payload = {
        "test_id": stats.test_id,
        "discrimination_pairs": stats.discrimination_pairs,
        "open_coverage": stats.open_coverage,
        "estimated_cost": stats.estimated_cost,
    }
    assert "confidence" not in payload
    assert "rank" not in str(payload).lower()
    assert "best" not in str(payload).lower()
    assert "winner" not in str(payload).lower()


def test_statistics_key_orders_discrimination_first():
    state = make_three_way_state()
    key_a = _stats_by_id(state, "T-A").selection_key()
    key_b = _stats_by_id(state, "T-B").selection_key()
    assert key_a < key_b
    assert key_a == (-2, -3, 2.0, "T-A")
