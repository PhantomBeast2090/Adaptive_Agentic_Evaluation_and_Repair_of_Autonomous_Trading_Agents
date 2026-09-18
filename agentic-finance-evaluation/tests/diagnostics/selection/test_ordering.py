"""Lexicographic ordering: D, then C, then cost, then test_id."""

from evaluation.diagnostics.selection import select_next_test

from ..fixtures import make_hypothesis, make_rival, make_state, make_test
from .fixtures import add_prediction, make_costly_test, make_three_way_state


def _state_with_costs(cost_a, cost_b):
    state = make_state()
    state.register_hypothesis(make_hypothesis())
    state.register_hypothesis(make_rival())
    state.register_test(make_costly_test("T-A", cost_a))
    state.register_test(make_costly_test("T-B", cost_b))
    for pid, hid in (("P-A1", "H-1"), ("P-A2", "H-2")):
        add_prediction(state, pid, hid, "T-A", "DECREASE")
    for pid, hid in (("P-B1", "H-1"), ("P-B2", "H-2")):
        add_prediction(state, pid, hid, "T-B", "DECREASE")
    # H-2 agrees on both: D=0 everywhere; coverage ties at 2.
    return state


def test_cost_breaks_coverage_ties():
    state = _state_with_costs(9.0, 1.0)
    out = select_next_test(state)
    assert out.selected_test_id == "T-B"
    assert out.alternative_test_ids == ("T-A",)


def test_test_id_breaks_cost_ties_deterministically():
    state = _state_with_costs(2.0, 2.0)
    out = select_next_test(state)
    assert out.selected_test_id == "T-A"
    assert out.alternative_test_ids == ("T-B",)


def test_discrimination_outranks_cost():
    state = make_three_way_state()
    # T-A (D=2, cost 2.0) beats any cost advantage T-B (D=0) could have.
    out = select_next_test(state)
    assert out.selected_test_id == "T-A"


def test_candidate_ordering_is_deterministic():
    first = select_next_test(make_three_way_state())
    second_state = make_three_way_state()
    # Fresh identical state must yield an equal (not re-recorded) outcome;
    # compare content rather than recording twice into one state.
    from evaluation.diagnostics.selection import select_next_test as select

    second = select(second_state)
    assert first.to_dict() == second.to_dict()
    assert first.fingerprint() == second.fingerprint()
    rationale_ids = [r.rationale_id for r in second_state.rationales]
    assert rationale_ids == [first.rationale_id]
    ordered = [c.test_id for c in second_state.rationales[0].candidates]
    assert ordered == ["T-A", "T-B"]


def test_single_open_hypothesis_selects_by_cost_then_id():
    state = make_state()
    state.register_hypothesis(make_hypothesis())
    state.register_test(make_costly_test("T-A", 5.0))
    state.register_test(make_costly_test("T-B", 1.0))
    add_prediction(state, "P-A1", "H-1", "T-A", "DECREASE")
    add_prediction(state, "P-B1", "H-1", "T-B", "DECREASE")
    out = select_next_test(state)
    assert out.selected_test_id == "T-B"
    assert out.confidence == 1.0
