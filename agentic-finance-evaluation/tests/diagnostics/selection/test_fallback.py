"""Fallback: no rival separation, and no candidates at all."""

from evaluation.contracts.stopping import StoppingReason
from evaluation.diagnostics.selection import select_next_test

from ..fixtures import make_hypothesis, make_state, make_test
from .fixtures import add_prediction


def test_fallback_selection_without_rival_separation():
    state = make_state()
    state.register_hypothesis(make_hypothesis())
    state.register_hypothesis(
        make_hypothesis(
            hypothesis_id="H-2",
            mechanism="Sizes positions unstably under volatility.",
        )
    )
    state.register_test(make_test(test_id="T-A"))
    state.register_test(make_test(test_id="T-B"))
    # Both agree everywhere: D=0 on both; T-A before T-B by test_id.
    for pid, hid, tid in (
        ("P-A1", "H-1", "T-A"),
        ("P-A2", "H-2", "T-A"),
        ("P-B1", "H-1", "T-B"),
        ("P-B2", "H-2", "T-B"),
    ):
        add_prediction(state, pid, hid, tid, "INCREASE")
    out = select_next_test(state)
    assert out.selected_test_id == "T-A"
    assert "no candidate provided directional rival separation" in (
        out.expected_discrimination
    )
    rationale = state.rationales[0]
    assert "no candidate provided directional rival separation" in (
        rationale.candidate("T-B").expected_discrimination
    )


def test_no_eligible_candidates_returns_structured_outcome():
    state = make_state()
    out = select_next_test(state)
    assert type(out).__name__ == "NoCandidateResult"
    assert out.reason
    assert out.candidates_considered == 0
    assert out.method == "adaptive-discrimination"
    assert out.version == "v1"


def test_open_but_untestable_suggests_unresolved():
    state = make_state()
    state.register_hypothesis(make_hypothesis())
    state.register_test(make_test())
    # Registered test, but no committed prediction → nothing eligible
    # while H-1 stays open.
    out = select_next_test(state)
    assert type(out).__name__ == "NoCandidateResult"
    assert out.suggested_stopping == StoppingReason.HYPOTHESIS_UNRESOLVED


def test_nothing_open_suggests_no_actionable_failure():
    from ..fixtures import make_result, make_update

    state = make_state()
    state.register_hypothesis(make_hypothesis())
    state.register_test(make_test())
    from .fixtures import add_prediction

    add_prediction(state, "P-1", "H-1", "T-1", "DECREASE")
    state.record_result(make_result())
    prior = state.hypothesis("H-1")
    update = make_update(update_id="U-1", prior=prior)
    from evaluation.contracts.hypotheses import HypothesisStatus
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
            updated=prior.with_status(HypothesisStatus.REJECTED),
            updated_confidence=prior.confidence,
            evidence_refs=update.evidence_refs,
            method=update.method,
            version=update.version,
        )
    )
    out = select_next_test(state)
    assert type(out).__name__ == "NoCandidateResult"
    assert out.suggested_stopping == StoppingReason.NO_ACTIONABLE_FAILURE
