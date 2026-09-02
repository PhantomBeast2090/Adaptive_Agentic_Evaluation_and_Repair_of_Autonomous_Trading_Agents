import pytest

from environment.portfolio.accounting import Portfolio


def test_buy_sell_hold_accounting_with_transaction_costs():
    portfolio = Portfolio(initial_cash=1000.0, transaction_cost_bps=10.0)

    buy_fee = portfolio.execute_trade("BUY", 5.0, 100.0)
    assert buy_fee == 0.5
    assert portfolio.cash == 499.5
    assert portfolio.holdings == 5.0
    assert portfolio.get_value(100.0) == 999.5

    hold_fee = portfolio.execute_trade("HOLD", 5.0, 110.0)
    assert hold_fee == 0.0
    assert portfolio.cash == 499.5
    assert portfolio.holdings == 5.0
    assert portfolio.get_value(110.0) == 1049.5

    sell_fee = portfolio.execute_trade("SELL", 2.0, 110.0)
    assert sell_fee == 0.22
    assert portfolio.cash == 719.28
    assert portfolio.holdings == 3.0
    assert portfolio.get_value(110.0) == 1049.28


def test_insufficient_cash_executes_maximum_affordable_quantity():
    portfolio = Portfolio(initial_cash=100.0, transaction_cost_bps=100.0)

    fee = portfolio.execute_trade("BUY", 2.0, 100.0)

    assert round(portfolio.holdings, 8) == round(100.0 / 1.01 / 100.0, 8)
    assert round(fee, 8) == round(0.9900990099009901, 8)
    assert abs(portfolio.cash) < 1e-10


def test_selling_more_than_holdings_only_sells_available_position():
    portfolio = Portfolio(initial_cash=1000.0, transaction_cost_bps=0.0)
    portfolio.execute_trade("BUY", 3.0, 100.0)

    fee = portfolio.execute_trade("SELL", 10.0, 120.0)

    assert fee == 0.0
    assert portfolio.holdings == 0.0
    assert portfolio.cash == 1060.0


def test_invalid_or_impossible_trades_are_noops():
    portfolio = Portfolio(initial_cash=1000.0, transaction_cost_bps=10.0)

    for action, quantity, price in [
        ("BUY", -1.0, 100.0),
        ("BUY", 1.0, -100.0),
        ("SELL", -1.0, 100.0),
        ("NOT_AN_ACTION", 1.0, 100.0),
        (None, 1.0, 100.0),
        ("BUY", 0.0, 100.0),
    ]:
        fee = portfolio.execute_trade(action, quantity, price)
        assert fee == 0.0
        assert portfolio.cash == 1000.0
        assert portfolio.holdings == 0.0


def test_invalid_portfolio_inputs_raise():
    with pytest.raises(ValueError):
        Portfolio(initial_cash=-1.0)

    with pytest.raises(ValueError):
        Portfolio(initial_cash=1000.0, transaction_cost_bps=-1.0)

    portfolio = Portfolio(initial_cash=1000.0)
    with pytest.raises(ValueError):
        portfolio.get_value(-1.0)
