"""Comparison matrix tests (mandate points 1-8, 21)."""

import pytest

from evaluation.diagnostics.contracts.hypothesis_updates import Compatibility
from evaluation.diagnostics.contracts.predictions import ExpectedDirection
from evaluation.diagnostics.interpretation.comparison import compare
from evaluation.diagnostics.interpretation.methodology import TAU

INC = ExpectedDirection.INCREASE
DEC = ExpectedDirection.DECREASE
NC = ExpectedDirection.NO_CHANGE


def test_increase_supports_and_contradicts():
    assert (
        compare(direction=INC, observed_value=1.2, control_value=1.0)
        .compatibility
        is Compatibility.SUPPORTS
    )
    assert (
        compare(direction=INC, observed_value=0.9, control_value=1.0)
        .compatibility
        is Compatibility.CONTRADICTS
    )
    # Inside the band: the claimed increase did not materialise.
    assert (
        compare(direction=INC, observed_value=1.005, control_value=1.0)
        .compatibility
        is Compatibility.CONTRADICTS
    )


def test_decrease_supports_and_contradicts():
    assert (
        compare(direction=DEC, observed_value=0.8, control_value=1.0)
        .compatibility
        is Compatibility.SUPPORTS
    )
    assert (
        compare(direction=DEC, observed_value=1.1, control_value=1.0)
        .compatibility
        is Compatibility.CONTRADICTS
    )
    assert (
        compare(direction=DEC, observed_value=0.995, control_value=1.0)
        .compatibility
        is Compatibility.CONTRADICTS
    )


def test_no_change_supports_and_contradicts():
    assert (
        compare(direction=NC, observed_value=1.005, control_value=1.0)
        .compatibility
        is Compatibility.SUPPORTS
    )
    assert (
        compare(direction=NC, observed_value=1.2, control_value=1.0)
        .compatibility
        is Compatibility.CONTRADICTS
    )


def test_zero_control_uses_exact_rule():
    assert (
        compare(direction=INC, observed_value=0.5, control_value=0.0)
        .compatibility
        is Compatibility.SUPPORTS
    )
    assert (
        compare(direction=NC, observed_value=0.0, control_value=0.0)
        .compatibility
        is Compatibility.SUPPORTS
    )
    assert (
        compare(direction=INC, observed_value=0.0, control_value=0.0)
        .compatibility
        is Compatibility.CONTRADICTS
    )
    assert (
        compare(direction=DEC, observed_value=0.0, control_value=0.0)
        .compatibility
        is Compatibility.CONTRADICTS
    )


def test_negative_control_is_sign_correct():
    # -100 -> -80 is an increase (+20% relative to |base|).
    assert (
        compare(direction=INC, observed_value=-80.0, control_value=-100.0)
        .compatibility
        is Compatibility.SUPPORTS
    )
    assert (
        compare(direction=DEC, observed_value=-120.0, control_value=-100.0)
        .compatibility
        is Compatibility.SUPPORTS
    )
    assert (
        compare(direction=INC, observed_value=-120.0, control_value=-100.0)
        .compatibility
        is Compatibility.CONTRADICTS
    )


def test_missing_observed_is_inconclusive():
    outcome = compare(
        direction=INC, observed_value=None, control_value=1.0
    )
    assert outcome.compatibility is Compatibility.INCONCLUSIVE
    assert outcome.detail


def test_undefined_control_is_inconclusive_with_reason():
    outcome = compare(
        direction=DEC,
        observed_value=0.5,
        control_value=None,
        control_reason="'turnover' explicitly undefined in baseline: no trades",
    )
    assert outcome.compatibility is Compatibility.INCONCLUSIVE
    assert "no trades" in outcome.detail
    with pytest.raises(ValueError):
        compare(direction=DEC, observed_value=0.5, control_value=None)


def test_band_boundary_is_deterministic():
    assert TAU == 0.01
    just_outside = compare(
        direction=INC, observed_value=1.0 * (1 + TAU) + 1e-12,
        control_value=1.0,
    )
    assert just_outside.compatibility is Compatibility.SUPPORTS
    just_inside = compare(
        direction=INC, observed_value=1.0 * (1 + TAU) - 1e-12,
        control_value=1.0,
    )
    assert just_inside.compatibility is Compatibility.CONTRADICTS
    first = compare(direction=NC, observed_value=1.0, control_value=1.0)
    second = compare(direction=NC, observed_value=1.0, control_value=1.0)
    assert first == second
    assert "rel_change=+0.000000" in first.detail


def test_invalid_inputs_fail_closed():
    with pytest.raises(TypeError):
        compare(direction="UP", observed_value=1.0, control_value=1.0)
    with pytest.raises(TypeError):
        compare(
            direction=INC, observed_value=float("nan"), control_value=1.0
        )
    with pytest.raises(TypeError):
        compare(direction=INC, observed_value=True, control_value=1.0)
