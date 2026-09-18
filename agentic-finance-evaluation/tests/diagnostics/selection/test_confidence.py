"""Proposal-confidence semantics: structural support, not truth probability."""

import pytest

from evaluation.contracts.hypotheses import Hypothesis
from evaluation.diagnostics.selection import select_next_test

from ..fixtures import make_state, make_test
from .fixtures import add_prediction


def _three_open_state():
    state = make_state(diagnostic_id="D-CONF")
    for hid, mechanism in (
        ("H-1", "Overreacts to noise bursts."),
        ("H-2", "Sizes positions unstably under volatility."),
        ("H-3", "Stale information reuse."),
    ):
        state.register_hypothesis(
            Hypothesis(
                hypothesis_id=hid,
                failure_class="excessive_turnover",
                mechanism=mechanism,
                evidence_refs=("E-1",),
                confidence=0.5,
            )
        )
    return state


def test_full_coverage_with_discrimination_is_one():
    state = _three_open_state()
    state.register_test(make_test(test_id="T-1"))
    add_prediction(state, "P-1", "H-1", "T-1", "DECREASE")
    add_prediction(state, "P-2", "H-2", "T-1", "INCREASE")
    add_prediction(state, "P-3", "H-3", "T-1", "INCREASE")
    out = select_next_test(state)
    assert out.selected_test_id == "T-1"
    assert out.confidence == 1.0


def test_partial_coverage_with_discrimination_is_ratio():
    state = _three_open_state()
    state.register_test(make_test(test_id="T-1"))
    add_prediction(state, "P-1", "H-1", "T-1", "DECREASE")
    add_prediction(state, "P-2", "H-2", "T-1", "INCREASE")
    out = select_next_test(state)
    assert out.confidence == pytest.approx(2.0 / 3.0)


def test_full_coverage_without_discrimination_is_zero():
    state = _three_open_state()
    state.register_test(make_test(test_id="T-1"))
    add_prediction(state, "P-1", "H-1", "T-1", "INCREASE")
    add_prediction(state, "P-2", "H-2", "T-1", "INCREASE")
    add_prediction(state, "P-3", "H-3", "T-1", "INCREASE")
    out = select_next_test(state)
    assert out.selected_test_id == "T-1"
    assert out.confidence == 0.0


def test_partial_coverage_without_discrimination_is_zero():
    state = _three_open_state()
    state.register_test(make_test(test_id="T-1"))
    add_prediction(state, "P-1", "H-1", "T-1", "INCREASE")
    add_prediction(state, "P-2", "H-2", "T-1", "INCREASE")
    out = select_next_test(state)
    assert out.confidence == 0.0


def test_single_open_hypothesis_is_zero():
    state = make_state(diagnostic_id="D-CONF-1")
    state.register_hypothesis(
        Hypothesis(
            hypothesis_id="H-1",
            failure_class="excessive_turnover",
            mechanism="Overreacts to noise bursts.",
            evidence_refs=("E-1",),
            confidence=0.5,
        )
    )
    state.register_test(make_test(test_id="T-1"))
    add_prediction(state, "P-1", "H-1", "T-1", "DECREASE")
    out = select_next_test(state)
    # D == 0 with a single open hypothesis: no rival separation exists.
    assert out.confidence == 0.0


def test_confidence_ignores_hypothesis_confidence():
    def _run_at(level):
        state = make_state(diagnostic_id="D-CONF-H")
        for hid in ("H-1", "H-2"):
            state.register_hypothesis(
                Hypothesis(
                    hypothesis_id=hid,
                    failure_class="excessive_turnover",
                    mechanism=f"Mechanism {hid}.",
                    evidence_refs=("E-1",),
                    confidence=level,
                )
            )
        state.register_test(make_test(test_id="T-1"))
        add_prediction(state, "P-1", "H-1", "T-1", "DECREASE")
        add_prediction(state, "P-2", "H-2", "T-1", "INCREASE")
        return select_next_test(state)

    low = _run_at(0.1)
    high = _run_at(0.9)
    assert low.confidence == high.confidence == 1.0
    assert low.selected_test_id == high.selected_test_id == "T-1"
    # Identities rightly differ (state content differs), but the
    # structural confidence value does not track hypothesis confidence.
