"""Tests for the Phase 2 execution-report extension to the environment contract.

Fill sizes and fees must stay identical to Phase 1.5; only observability is new.
"""

import pandas as pd
import pytest

from environment.core import FinancialEnvironment
from environment.portfolio.accounting import (
    BINDING_CASH,
    BINDING_POSITION,
    STATUS_EXECUTED_FULL,
    STATUS_EXECUTED_PARTIAL,
    STATUS_NOOP_HOLD,
    STATUS_NOOP_INVALID_ACTION,
    STATUS_NOOP_INVALID_QUANTITY,
    STATUS_NOOP_NO_CASH,
    STATUS_NOOP_NO_POSITION,
    STATUS_NOOP_NON_POSITIVE_PRICE,
    STATUS_NOOP_NON_POSITIVE_QUANTITY,
    Portfolio,
)


def test_full_buy_reports_requested_equals_executed():
    portfolio = Portfolio(initial_cash=1000.0, transaction_cost_bps=10.0)

    report = portfolio.execute("BUY", 5.0, 100.0)

    assert report.action_normalized == "BUY"
    assert report.status == STATUS_EXECUTED_FULL
    assert report.requested_quantity == 5.0
    assert report.executed_quantity == 5.0
    assert report.execution_price == 100.0
    assert report.transaction_cost == 0.5
    assert report.constraint_binding is None
    assert portfolio.cash == 499.5


def test_oversized_buy_reports_partial_fill_bound_by_cash():
    portfolio = Portfolio(initial_cash=100.0, transaction_cost_bps=100.0)

    report = portfolio.execute("BUY", 2.0, 100.0)

    expected_qty = (100.0 / 1.01) / 100.0
    assert report.status == STATUS_EXECUTED_PARTIAL
    assert report.constraint_binding == BINDING_CASH
    assert report.requested_quantity == 2.0
    assert round(report.executed_quantity, 12) == round(expected_qty, 12)
    assert report.executed_quantity < report.requested_quantity


def test_buy_with_zero_cash_reports_no_cash_noop():
    portfolio = Portfolio(initial_cash=0.0, transaction_cost_bps=10.0)

    report = portfolio.execute("BUY", 1.0, 100.0)

    assert report.status == STATUS_NOOP_NO_CASH
    assert report.constraint_binding == BINDING_CASH
    assert report.executed_quantity == 0.0
    assert report.transaction_cost == 0.0


def test_oversized_sell_reports_partial_fill_bound_by_position():
    portfolio = Portfolio(initial_cash=1000.0, transaction_cost_bps=0.0)
    portfolio.execute("BUY", 3.0, 100.0)

    report = portfolio.execute("SELL", 10.0, 120.0)

    assert report.status == STATUS_EXECUTED_PARTIAL
    assert report.constraint_binding == BINDING_POSITION
    assert report.requested_quantity == 10.0
    assert report.executed_quantity == 3.0
    assert portfolio.holdings == 0.0
    assert portfolio.cash == 1060.0


def test_sell_without_position_reports_no_position_noop():
    portfolio = Portfolio(initial_cash=1000.0, transaction_cost_bps=0.0)

    report = portfolio.execute("SELL", 4.0, 100.0)

    assert report.status == STATUS_NOOP_NO_POSITION
    assert report.constraint_binding == BINDING_POSITION
    assert report.requested_quantity == 4.0
    assert report.executed_quantity == 0.0


def test_exact_position_sell_is_reported_as_full_fill():
    portfolio = Portfolio(initial_cash=1000.0, transaction_cost_bps=0.0)
    portfolio.execute("BUY", 3.0, 100.0)

    report = portfolio.execute("SELL", 3.0, 100.0)

    assert report.status == STATUS_EXECUTED_FULL
    assert report.constraint_binding is None


@pytest.mark.parametrize(
    "action,quantity,price,expected_status",
    [
        ("HOLD", 0.0, 100.0, STATUS_NOOP_HOLD),
        ("HOLD", 5.0, 100.0, STATUS_NOOP_HOLD),
        ("NOT_AN_ACTION", 1.0, 100.0, STATUS_NOOP_INVALID_ACTION),
        (None, 1.0, 100.0, STATUS_NOOP_INVALID_ACTION),
        ("BUY", "many", 100.0, STATUS_NOOP_INVALID_QUANTITY),
        ("BUY", -1.0, 100.0, STATUS_NOOP_NON_POSITIVE_QUANTITY),
        ("BUY", 0.0, 100.0, STATUS_NOOP_NON_POSITIVE_QUANTITY),
        ("SELL", -1.0, 100.0, STATUS_NOOP_NON_POSITIVE_QUANTITY),
        ("BUY", 1.0, -100.0, STATUS_NOOP_NON_POSITIVE_PRICE),
    ],
)
def test_noop_submissions_are_classified_and_leave_portfolio_untouched(
    action, quantity, price, expected_status
):
    portfolio = Portfolio(initial_cash=1000.0, transaction_cost_bps=10.0)

    report = portfolio.execute(action, quantity, price)

    assert report.status == expected_status
    assert report.executed_quantity == 0.0
    assert report.transaction_cost == 0.0
    assert portfolio.cash == 1000.0
    assert portfolio.holdings == 0.0


def test_execute_trade_wrapper_still_returns_only_the_fee():
    portfolio = Portfolio(initial_cash=1000.0, transaction_cost_bps=10.0)

    assert portfolio.execute_trade("BUY", 5.0, 100.0) == 0.5
    assert portfolio.execute_trade("HOLD", 5.0, 110.0) == 0.0


def _market(tmp_path, name="market.parquet"):
    dates = pd.date_range("2020-01-01", periods=3)
    df = pd.DataFrame(
        {"SPY": [100.0, 110.0, 105.0], "^VIX": [12.0, 30.0, 20.0]},
        index=dates,
    )
    path = tmp_path / name
    df.to_parquet(path)
    return str(path)


def test_environment_outcome_carries_execution_fields(tmp_path):
    env = FinancialEnvironment(_market(tmp_path), initial_cash=1000.0, transaction_cost_bps=0.0)
    env.reset()

    _, outcome, done, _ = env.step("BUY", 4.0)

    assert done is False
    assert outcome["action_normalized"] == "BUY"
    assert outcome["requested_quantity"] == 4.0
    assert outcome["executed_quantity"] == 4.0
    assert outcome["execution_status"] == STATUS_EXECUTED_FULL
    assert outcome["constraint_binding"] is None


def test_environment_reports_cash_bound_partial_fill(tmp_path):
    env = FinancialEnvironment(_market(tmp_path), initial_cash=1000.0, transaction_cost_bps=0.0)
    env.reset()

    _, outcome, _, _ = env.step("BUY", 50.0)

    assert outcome["execution_status"] == STATUS_EXECUTED_PARTIAL
    assert outcome["constraint_binding"] == BINDING_CASH
    assert outcome["requested_quantity"] == 50.0
    assert outcome["executed_quantity"] == 10.0


def test_environment_reports_invalid_action_without_changing_portfolio(tmp_path):
    env = FinancialEnvironment(_market(tmp_path), initial_cash=1000.0, transaction_cost_bps=0.0)
    env.reset()

    _, outcome, _, _ = env.step("YOLO", 10.0)

    assert outcome["execution_status"] == STATUS_NOOP_INVALID_ACTION
    assert outcome["action_normalized"] == "INVALID"
    assert outcome["step_pnl"] == 0.0
    assert env.portfolio.cash == 1000.0
