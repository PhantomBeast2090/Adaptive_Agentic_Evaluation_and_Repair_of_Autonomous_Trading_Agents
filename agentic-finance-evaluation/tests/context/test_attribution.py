"""E4-O metric-level attribution tests (deterministic, no episodes)."""

import pytest

from evaluation.context.attribution import (
    CellAttribution,
    activity_share,
    attribution_fingerprint,
    exposure_normalised_return,
    mechanical_benchmark,
    paired_metric_delta,
    sharpe_is_fragile,
    turnover_normalised_return,
    attribute_cell,
)


def _metrics(**overrides):
    base = {
        "cumulative_return": -0.02,
        "max_drawdown": 0.03,
        "sharpe_per_session": -0.2,
        "turnover": 0.8,
        "order_count": 24.0,
        "inactivity_rate": 0.25,
        "gross_exposure_max": 0.9,
        "gross_exposure_mean": 0.6,
        "invalid_order_count": 0.0,
        "reversal_rate": None,
    }
    base.update(overrides)
    return base


def test_activity_share_arithmetic():
    assert activity_share(_metrics()) == pytest.approx(0.75)
    assert activity_share({"inactivity_rate": None}) is None
    assert activity_share({"inactivity_rate": 1.0}) == pytest.approx(0.0)
    with pytest.raises(TypeError):
        activity_share("nope")


def test_turnover_normalised_return_guards():
    assert turnover_normalised_return(_metrics()) == pytest.approx(
        -0.02 / 0.8
    )
    assert turnover_normalised_return(
        _metrics(turnover=0.0)) is None
    assert turnover_normalised_return(
        _metrics(cumulative_return=None)) is None
    assert turnover_normalised_return(
        _metrics(turnover=None)) is None


def test_exposure_normalised_return_guards():
    assert exposure_normalised_return(_metrics()) == pytest.approx(
        -0.02 / 0.6
    )
    assert exposure_normalised_return(
        _metrics(gross_exposure_mean=0.0)) is None
    assert exposure_normalised_return({}) is None


def test_none_preservation_and_missing_metrics():
    cell = attribute_cell("A", "diagnostic", _metrics())
    assert cell.observed["reversal_rate"] is None
    assert cell.observed["cumulative_return"] == pytest.approx(-0.02)
    assert cell.fragile_sharpe is False
    assert cell.fingerprint()


def test_fragile_sharpe_low_activity():
    assert sharpe_is_fragile(_metrics(inactivity_rate=0.95)) is True
    assert sharpe_is_fragile(_metrics(inactivity_rate=0.25)) is False
    assert sharpe_is_fragile({}) is True
    assert sharpe_is_fragile(
        _metrics(inactivity_rate=0.81)) is True
    assert sharpe_is_fragile(
        _metrics(inactivity_rate=0.79)) is False


def test_negative_returns_preserved():
    cell = attribute_cell("C", "heldout", _metrics(
        cumulative_return=-0.001, turnover=0.05,
        gross_exposure_mean=0.04, inactivity_rate=0.95,
    ))
    assert cell.turnover_normalised_return == pytest.approx(-0.02)
    assert cell.exposure_normalised_return == pytest.approx(-0.025)
    assert cell.fragile_sharpe is True


def test_mechanical_benchmark_labels_and_guards():
    out = mechanical_benchmark(
        {"cumulative_return": -0.04, "gross_exposure_mean": 0.8},
        {"cumulative_return": -0.01, "gross_exposure_mean": 0.2},
    )
    assert out["expected_context_return"] == pytest.approx(-0.01)
    assert out["residual"] == pytest.approx(0.0)
    assert out["residual_defined"] is True
    assert "linear exposure scaling" in out["assumption"]
    out = mechanical_benchmark(
        {"cumulative_return": -0.04, "gross_exposure_mean": 0.0},
        {"cumulative_return": -0.01, "gross_exposure_mean": 0.2},
    )
    assert out["residual_defined"] is False
    assert out["residual"] is None
    out = mechanical_benchmark({}, {})
    assert out["residual_defined"] is False
    with pytest.raises(TypeError):
        mechanical_benchmark("x", {})


def test_paired_metric_delta_none_preserving():
    out = paired_metric_delta({"a": 1.0, "b": None}, {"a": 2.0})
    assert out == {"a": 1.0, "b": None}


def test_determinism_and_fingerprint():
    first = attribute_cell("A", "w", _metrics()).fingerprint()
    second = attribute_cell("A", "w", _metrics()).fingerprint()
    assert first == second
    assert attribution_fingerprint({"a": 1}) == attribution_fingerprint(
        {"a": 1}
    )
    with pytest.raises(TypeError):
        attribution_fingerprint("x")
    with pytest.raises(TypeError):
        attribute_cell("A", "w", "x")
    with pytest.raises(ValueError):
        attribute_cell("", "w", _metrics())
