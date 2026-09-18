"""Adaptivity: selection follows updated diagnostic state, never replays."""

from evaluation.contracts.hypotheses import HypothesisStatus
from evaluation.diagnostics.selection import select_next_test
from evaluation.diagnostics.selection.candidates import candidate_statistics

from ..fixtures import (
    make_hypothesis,
    make_result,
    make_state,
    make_test,
    make_update,
)
from .fixtures import add_prediction, make_costly_test


def _promote(state, hid, status, uid):
    prior = state.hypothesis(hid)
    update = make_update(update_id=uid, prior=prior)
    from evaluation.diagnostics.contracts.hypothesis_updates import (
        HypothesisUpdate,
    )

    state.record_update(
        HypothesisUpdate(
            update_id=update.update_id,
            hypothesis_id=update.hypothesis_id,
            prior=prior,
            prior_fingerprint=prior.fingerprint(),
            prediction_id=update.prediction_id,
            result_id=update.result_id,
            compatibility=update.compatibility,
            assessment=update.assessment,
            updated=prior.with_status(HypothesisStatus(status)),
            updated_confidence=prior.confidence,
            evidence_refs=update.evidence_refs,
            method=update.method,
            version=update.version,
        )
    )


def _adaptive_state():
    state = make_state()
    state.register_hypothesis(make_hypothesis())
    state.register_hypothesis(
        make_hypothesis(
            hypothesis_id="H-2",
            mechanism="Sizes positions unstably under volatility.",
        )
    )
    state.register_test(make_costly_test("T-1", 5.0))
    state.register_test(make_costly_test("T-2", 1.0))
    add_prediction(state, "P-1", "H-1", "T-1", "DECREASE")
    add_prediction(state, "P-2", "H-2", "T-1", "INCREASE")
    add_prediction(state, "P-3", "H-1", "T-2", "DECREASE")
    add_prediction(state, "P-4", "H-2", "T-2", "DECREASE")
    return state


def test_selection_changes_after_result_and_update():
    state = _adaptive_state()
    first = select_next_test(state)
    # T-1 separates (D=1); T-2 agrees (D=0) → T-1 preferred.
    assert first.selected_test_id == "T-1"
    # Simulate completed execution + interpretation via public mechanics.
    state.record_result(
        make_result(test=make_costly_test("T-1", 5.0), prediction_ids=("P-1",))
    )
    _promote(state, "H-1", "SUPPORTED", "U-1")
    second = select_next_test(state)
    # T-1 is consumed; H-1 is closed; only T-2 over H-2 remains eligible.
    assert second.selected_test_id == "T-2"
    assert second.proposal_id != first.proposal_id
    assert second.rationale_id != first.rationale_id


def test_candidate_changes_after_lifecycle_change_only():
    state = _adaptive_state()
    before = select_next_test(state)
    assert before.selected_test_id == "T-1"
    # Weaken H-2 through a scratch test vehicle (T-9 becomes consumed);
    # T-1 still separates the open pair, so selection is stable —
    # proving the selector reads state rather than replaying order.
    after = select_next_test_fresh_copy()
    assert after.selected_test_id == "T-1"


def _promote_without_result(state):
    from .fixtures import add_prediction

    state.register_test(make_costly_test("T-9", 7.0))
    add_prediction(state, "P-9", "H-2", "T-9", "INCREASE")
    state.record_result(
        make_result(test=make_costly_test("T-9", 7.0), prediction_ids=("P-9",))
    )
    _promote(state, "H-2", "WEAKENED", "U-9")


def select_next_test_fresh_copy():
    # Rebuild the identical scenario including the lifecycle change, so
    # the comparison is between equal states rather than duplicate records.
    state = _adaptive_state()
    _promote_without_result(state)
    return select_next_test(state)


def test_consumed_tests_cannot_be_selected_again():
    state = _adaptive_state()
    first = select_next_test(state)
    assert first.selected_test_id == "T-1"
    state.record_result(
        make_result(test=make_costly_test("T-1", 5.0), prediction_ids=("P-1",))
    )
    _promote(state, "H-1", "SUPPORTED", "U-1")
    _promote(state, "H-2", "SUPPORTED", "U-2")
    # Both hypotheses closed and T-1 consumed; T-2 has no open
    # predictions left → no candidates at all.
    out = select_next_test(state)
    assert type(out).__name__ == "NoCandidateResult"


def test_single_open_hypothesis_adapts_on_closure():
    state = make_state()
    state.register_hypothesis(make_hypothesis())
    state.register_test(make_costly_test("T-1", 5.0))
    add_prediction(state, "P-1", "H-1", "T-1", "DECREASE")
    first = select_next_test(state)
    assert first.selected_test_id == "T-1"
    state.record_result(
        make_result(test=make_costly_test("T-1", 5.0), prediction_ids=("P-1",))
    )
    _promote(state, "H-1", "REJECTED", "U-1")
    out = select_next_test(state)
    assert type(out).__name__ == "NoCandidateResult"
    assert out.suggested_stopping is not None


def _discrimination(state, test_id):
    test = next(t for t in state.available_tests if t.test_id == test_id)
    return candidate_statistics(state, test).discrimination_pairs


def _eligible_ids(state):
    from evaluation.diagnostics.selection.candidates import (
        eligible_candidates,
    )

    eligible, _ = eligible_candidates(state)
    return {t.test_id for t in eligible}


def _close_hypothesis_via_vehicle(state, hid, status, uid):
    from evaluation.diagnostics.contracts.hypothesis_updates import (
        HypothesisUpdate,
    )

    prior = state.hypothesis(hid)
    state.record_result(
        make_result(
            result_id="R-9",
            test=make_costly_test("T-9", 7.0),
            prediction_ids=("P-9",),
        )
    )
    state.record_update(
        HypothesisUpdate(
            update_id=uid,
            hypothesis_id=hid,
            prior=prior,
            prior_fingerprint=prior.fingerprint(),
            prediction_id="P-9",
            result_id="R-9",
            compatibility="SUPPORTS",
            assessment="Vehicle update closing the hypothesis.",
            updated=prior.with_status(HypothesisStatus(status)),
            updated_confidence=prior.confidence,
            evidence_refs=("R-9",),
            method="test-fixture",
            version="v1",
        )
    )


def test_selection_flips_on_hypothesis_closure_with_tests_eligible():
    # H-1/H-2/H-3 OPEN; T-1 splits 2-vs-1 (D=2), T-2 unanimous (D=0).
    # T-2 is cheaper so it wins every tie — isolating discrimination
    # as the only reason T-1 is preferred first.
    state = make_state(diagnostic_id="D-STRONG")
    for hid, mechanism in (
        ("H-1", "Overreacts to noise bursts."),
        ("H-2", "Sizes positions unstably under volatility."),
        ("H-3", "Stale information reuse."),
    ):
        state.register_hypothesis(make_hypothesis(hid, mechanism))
    state.register_test(make_costly_test("T-1", 5.0))
    state.register_test(make_costly_test("T-2", 1.0))
    state.register_test(make_costly_test("T-9", 7.0))
    add_prediction(state, "P-1", "H-1", "T-1", "INCREASE")
    add_prediction(state, "P-2", "H-2", "T-1", "DECREASE")
    add_prediction(state, "P-3", "H-3", "T-1", "INCREASE")
    add_prediction(state, "P-4", "H-1", "T-2", "INCREASE")
    add_prediction(state, "P-5", "H-2", "T-2", "INCREASE")
    add_prediction(state, "P-6", "H-3", "T-2", "INCREASE")
    add_prediction(state, "P-9", "H-2", "T-9", "INCREASE")

    first = select_next_test(state)
    assert first.selected_test_id == "T-1"
    assert _discrimination(state, "T-1") == 2
    assert _discrimination(state, "T-2") == 0

    # Close H-2 through the vehicle test only: T-1 and T-2 are never
    # executed and stay eligible throughout.
    _close_hypothesis_via_vehicle(state, "H-2", "SUPPORTED", "U-9")
    assert state.hypothesis("H-2").status is HypothesisStatus.SUPPORTED
    # T-9 is consumed by the vehicle result; T-1 and T-2 were never
    # executed and remain eligible.
    assert "T-1" in _eligible_ids(state)
    assert "T-2" in _eligible_ids(state)

    # Only H-1/H-3 remain open and agree on both tests: discrimination
    # collapses to zero on each, so the cheaper T-2 wins.
    assert _discrimination(state, "T-1") == 0
    assert _discrimination(state, "T-2") == 0
    second = select_next_test(state)
    assert second.selected_test_id == "T-2"
    assert second.proposal_id != first.proposal_id
