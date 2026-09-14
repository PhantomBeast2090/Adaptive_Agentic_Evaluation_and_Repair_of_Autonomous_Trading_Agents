"""E1 metric tests: hand-computed values and explicit undefined cases."""

import statistics

import pytest

from evaluation.baseline.metrics import MetricResult, compute_all
from evaluation.contracts.decision_record import DecisionRecord

PRICE = 2489.25
FEE = 10.0 * PRICE * 5.0 / 10000.0


def _record(day, fp, before, after, with_trade=False):
    orders = (
        {
            "asset_id": "nse_equity",
            "instrument": "RELIANCE:EQ",
            "side": "BUY",
            "quantity": 10.0,
        },
    ) if with_trade else ()
    return DecisionRecord(
        decision_timestamp=day,
        state_fingerprint=fp,
        visible_assets=("nse_equity:RELIANCE:EQ",),
        unavailable_assets=("brent",),
        submitted_orders=orders,
        validation=({"status": "VALIDATED"},) if with_trade else (),
        executions=(
            {
                "asset_id": "nse_equity",
                "instrument": "nse_equity:RELIANCE:EQ",
                "action_normalized": "BUY",
                "requested_quantity": 10.0,
                "executed_quantity": 10.0,
                "execution_price": PRICE,
                "transaction_cost": FEE,
                "execution_status": "EXECUTED_FULL",
                "constraint_binding": None,
            },
        ) if with_trade else (),
        execution_price=PRICE if with_trade else None,
        transaction_cost=FEE if with_trade else 0.0,
        portfolio_before={"cash": before, "total_equity": before},
        portfolio_after={"cash": after, "total_equity": after},
        reward=after - before,
        environment_metadata={"market_fingerprint": "mfp-test"},
    )


def _three_records():
    return (
        _record("2023-05-15", "fp-1", 100000.0, 101000.0),
        _record("2023-05-16", "fp-2", 101000.0, 99000.0),
        _record("2023-05-17", "fp-3", 99000.0, 99500.0, with_trade=True),
    )


def _by_name(metrics):
    return {metric.name: metric for metric in metrics}


def test_hand_computed_metrics():
    metrics = _by_name(compute_all(_three_records(), 100000.0))
    assert metrics["cumulative_return"].value == pytest.approx(-0.005)
    assert metrics["max_drawdown"].value == pytest.approx(2000.0 / 101000.0)
    assert metrics["worst_session_return"].value == pytest.approx(
        -2000.0 / 101000.0
    )
    assert metrics["inactivity_rate"].value == pytest.approx(2.0 / 3.0)
    assert metrics["order_count"].value == 1.0
    assert metrics["transaction_cost_total"].value == pytest.approx(FEE)
    assert metrics["executed_notional"].value == pytest.approx(10.0 * PRICE)
    assert metrics["turnover"].value == pytest.approx(24892.5 / 99875.0)
    assert metrics["invalid_order_rate"].value == 0.0
    assert metrics["position_persistence"].value == 0.0
    assert metrics["unavailable_info_rate"].value == 1.0
    assert metrics["unavailable_info_session_count"].value == 3.0
    returns = [0.01, -2000.0 / 101000.0, 500.0 / 99000.0]
    assert metrics["volatility_per_session"].value == pytest.approx(
        statistics.pstdev(returns)
    )
    assert metrics["sharpe_per_session"].value == pytest.approx(
        statistics.fmean(returns) / statistics.pstdev(returns)
    )
    downside = statistics.fmean([min(0.0, r) ** 2 for r in returns]) ** 0.5
    assert metrics["sortino_per_session"].value == pytest.approx(
        statistics.fmean(returns) / downside
    )


def test_undefined_cases_represented_explicitly():
    metrics = _by_name(compute_all((), 100000.0))
    assert metrics["cumulative_return"].value is None
    assert metrics["cumulative_return"].undefined_reason == (
        "no decision records"
    )
    assert metrics["invalid_order_rate"].value is None
    assert metrics["concentration_cost_basis_max"].value is None
    assert metrics["reversal_rate"].value is None
    assert metrics["unavailable_info_rate"].value is None
    for metric in metrics.values():
        if metric.value is None:
            assert metric.undefined_reason

    single = _by_name(
        compute_all((_record("2023-05-15", "fp-1", 100000.0, 100000.0),), 100000.0)
    )
    assert single["sharpe_per_session"].value is None
    assert single["sortino_per_session"].value is None
    assert single["volatility_per_session"].value is None

    flat = (
        _record("2023-05-15", "fp-1", 100000.0, 100000.0),
        _record("2023-05-16", "fp-2", 100000.0, 100000.0),
    )
    flat_metrics = _by_name(compute_all(flat, 100000.0))
    assert flat_metrics["sharpe_per_session"].value is None
    assert "zero return dispersion" in (
        flat_metrics["sharpe_per_session"].undefined_reason
    )
    assert flat_metrics["sortino_per_session"].value is None
    assert flat_metrics["cumulative_return"].value == 0.0
    assert flat_metrics["max_drawdown"].value == 0.0


def test_no_failure_labels_in_metrics():
    metrics = compute_all(_three_records(), 100000.0)
    assert len(metrics) == 25
    for metric in metrics:
        assert set(metric.to_dict()) == {
            "name", "value", "unit", "undefined_reason", "derivation",
        }
        assert "threshold" not in metric.name
        assert "fail" not in metric.name and "pass" not in metric.name
        assert metric.derivation.startswith("e1.")
    assert MetricResult.from_dict(metrics[0].to_dict()) == metrics[0]
