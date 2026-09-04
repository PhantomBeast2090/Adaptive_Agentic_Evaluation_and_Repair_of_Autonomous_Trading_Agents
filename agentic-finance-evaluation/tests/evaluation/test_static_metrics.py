"""Tests for the static evaluation metrics.

Every asserted number is hand-calculable. The market fixtures are three rows
long with zero transaction cost, and the agents replay a fixed decision script,
so each portfolio value, return, and count below can be checked with arithmetic.

The primary fixture is deliberately built so the derived series are round
numbers:

    prices      100    110     99
    actions     BUY 10 HOLD   HOLD
    value path  1000 → 1100 → 990 → 990   (initial value, then one per step)
    returns          +0.1   -0.1   0.0
"""

import math

import pandas as pd
import pytest

from agents.financial_agent.base import BaseTradingAgent
from environment.core import FinancialEnvironment
from evaluation.episode_runner import Trajectory, run_episode
from evaluation.metrics import static_metrics as m

SQRT_252 = math.sqrt(252)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


class _ScriptedAgent(BaseTradingAgent):
    """Replays a fixed list of decisions, one per step, in order."""

    def __init__(self, decisions):
        super().__init__("scripted", "v1")
        self._decisions = list(decisions)
        self._index = 0

    def reset(self) -> None:
        self._index = 0

    def act(self, observation):
        decision = self._decisions[self._index]
        self._index += 1
        return decision

    def adapt(self, intervention) -> None:
        return None


def _hold(n):
    return [{"action": "HOLD", "quantity": 0.0, "rationale": ""}] * n


def _buy(quantity):
    return {"action": "BUY", "quantity": quantity, "rationale": ""}


def _sell(quantity):
    return {"action": "SELL", "quantity": quantity, "rationale": ""}


def _market(tmp_path, prices, name="market.parquet"):
    dates = pd.date_range("2020-01-01", periods=len(prices))
    df = pd.DataFrame({"SPY": prices, "^VIX": [10.0] * len(prices)}, index=dates)
    path = tmp_path / name
    df.to_parquet(path)
    return str(path)


def _run(tmp_path, prices, decisions, initial_cash=1000.0, name="market.parquet"):
    env = FinancialEnvironment(
        _market(tmp_path, prices, name),
        initial_cash=initial_cash,
        transaction_cost_bps=0.0,
    )
    return run_episode(_ScriptedAgent(decisions), env, scenario_id="s1")


@pytest.fixture
def traded(tmp_path):
    """BUY then hold through a rise and a fall. See the module docstring."""
    return _run(tmp_path, [100.0, 110.0, 99.0], [_buy(10.0)] + _hold(2))


@pytest.fixture
def flat(tmp_path):
    """Never trades: cash sits at 1000 for the whole episode."""
    return _run(tmp_path, [100.0, 110.0, 99.0], _hold(3))


@pytest.fixture
def constrained(tmp_path):
    """An oversized buy, an oversized sell, then a sell with nothing to sell."""
    return _run(
        tmp_path,
        [100.0, 100.0, 100.0],
        [_buy(20.0), _sell(50.0), _sell(5.0)],
    )


@pytest.fixture
def malformed(tmp_path):
    """Three submissions the environment cannot read as well-formed orders."""
    return _run(
        tmp_path,
        [100.0, 110.0, 99.0],
        [
            "buy some",
            {"action": "BUY", "quantity": "lots"},
            {"action": "BUY", "quantity": -5.0},
        ],
    )


@pytest.fixture
def empty():
    return Trajectory("ep", "s1", "agent", "v1")


# --------------------------------------------------------------------------- #
# Series extraction
# --------------------------------------------------------------------------- #


def test_value_path_starts_at_the_pre_action_value(traded):
    assert m.value_path(traded) == [1000.0, 1100.0, 990.0, 990.0]
    assert len(m.value_path(traded)) == m.episode_length(traded) + 1


def test_value_path_differences_equal_the_recorded_step_pnl(traded):
    path = m.value_path(traded)
    recorded = [step["outcome"]["step_pnl"] for step in traded.steps]
    differences = [path[i + 1] - path[i] for i in range(len(path) - 1)]

    assert differences == pytest.approx(recorded)


def test_step_returns_are_exact(traded):
    assert m.step_returns(traded) == pytest.approx([0.1, -0.1, 0.0])


def test_market_prices_are_the_replayed_window(traded):
    assert m.market_prices(traded) == [100.0, 110.0, 99.0]


# --------------------------------------------------------------------------- #
# Performance
# --------------------------------------------------------------------------- #


def test_performance_metrics(traded):
    assert m.final_portfolio_value(traded) == 990.0
    assert m.cumulative_pnl(traded) == pytest.approx(-10.0)
    assert m.total_return(traded) == pytest.approx(-0.01)


def test_annualized_return_compounds_the_episode_return(traded):
    # 3 steps, so the growth factor 0.99 compounds 252/3 = 84 times.
    assert m.annualized_return(traded) == pytest.approx(0.99 ** 84 - 1)


def test_annualized_return_is_undefined_for_a_total_loss(tmp_path):
    # Buy everything at 100, then the price collapses to 0.01 (the environment
    # forbids zero prices, so this is as close to a total loss as we can reach).
    trajectory = _run(tmp_path, [100.0, 0.01, 0.01], [_buy(10.0)] + _hold(2))

    assert m.total_return(trajectory) == pytest.approx(-0.9999)
    # A growth factor at or below zero cannot be annualized.
    assert m.annualized_return(trajectory) is None


def test_market_reference_and_excess_return(traded):
    # The market fell 1% over the window and so did the portfolio.
    assert m.market_price_return(traded) == pytest.approx(-0.01)
    assert m.excess_return_vs_market(traded) == pytest.approx(0.0)


def test_excess_return_is_negative_when_the_agent_lags_the_market(flat):
    # Holding cash through a 1% decline beats the market by 1%.
    assert m.total_return(flat) == 0.0
    assert m.market_price_return(flat) == pytest.approx(-0.01)
    assert m.excess_return_vs_market(flat) == pytest.approx(0.01)


# --------------------------------------------------------------------------- #
# Risk
# --------------------------------------------------------------------------- #


def test_volatility_is_the_sample_standard_deviation(traded):
    # returns [0.1, -0.1, 0.0], mean 0, so ddof=1 variance = 0.02/2 = 0.01.
    assert m.volatility(traded, annualize=False) == pytest.approx(0.1)
    assert m.volatility(traded) == pytest.approx(0.1 * SQRT_252)


def test_maximum_drawdown_is_measured_from_the_running_peak(traded):
    # Peak 1100, trough 990.
    assert m.maximum_drawdown(traded) == pytest.approx(0.1)


def test_downside_deviation_uses_the_full_sample_denominator(traded):
    # One negative return of -0.1 across 3 returns: sqrt(0.01 / 3).
    assert m.downside_deviation(traded, annualize=False) == pytest.approx(0.1 / math.sqrt(3))
    assert m.downside_deviation(traded) == pytest.approx(0.1 * math.sqrt(84))


def test_sharpe_ratio_is_zero_when_mean_excess_return_is_zero(traded):
    assert m.sharpe_ratio(traded) == pytest.approx(0.0)


def test_sharpe_ratio_subtracts_the_periodized_risk_free_rate(traded):
    # mean return is 0, so mean excess = -rf/252 and sharpe = -(rf/252)/0.1*sqrt(252).
    expected = (-(0.0252 / 252) / 0.1) * SQRT_252
    assert m.sharpe_ratio(traded, risk_free_rate=0.0252) == pytest.approx(expected)


def test_sharpe_ratio_is_undefined_at_zero_dispersion(flat):
    # A cash-only episode has zero return dispersion. An infinite Sharpe ratio
    # is not reported as a large number.
    assert m.volatility(flat) == 0.0
    assert m.sharpe_ratio(flat) is None


def test_risk_metrics_are_measured_zero_not_undefined_for_a_flat_episode(flat):
    assert m.maximum_drawdown(flat) == 0.0
    assert m.downside_deviation(flat) == 0.0


def test_conditional_post_loss_metrics_on_a_losing_step(traded):
    # Step 1 loses 110 from a peak observation of 1100; the next observed value
    # is 990, so the post-loss drawdown is 110/1100.
    assert m.conditional_post_loss_drawdown(traded) == pytest.approx(0.1)
    # Exposure before the loss 10*110, after 10*99.
    assert m.conditional_position_exposure_ratio(traded) == pytest.approx(0.9)


def test_conditional_metrics_are_undefined_without_a_losing_step(flat):
    # The underlying engine returns 0.0 and 1.0 here. Reporting those would read
    # as measured post-loss behaviour on an episode that never lost.
    assert m.conditional_post_loss_drawdown(flat) is None
    assert m.conditional_position_exposure_ratio(flat) is None


# --------------------------------------------------------------------------- #
# Trading behaviour
# --------------------------------------------------------------------------- #


def test_trade_counts_and_notional(traded):
    assert m.trade_count(traded) == 1
    assert m.trade_frequency(traded) == pytest.approx(1 / 3)
    assert m.total_traded_notional(traded) == pytest.approx(1000.0)
    assert m.total_transaction_costs(traded) == 0.0


def test_turnover_is_notional_over_mean_portfolio_value(traded):
    # mean of [1000, 1100, 990, 990] is 1020.
    assert m.turnover_ratio(traded) == pytest.approx(1000.0 / 1020.0)


def test_zero_trade_episode_reports_measured_zeros(flat):
    assert m.trade_count(flat) == 0
    assert m.trade_frequency(flat) == 0.0
    assert m.total_traded_notional(flat) == 0.0
    assert m.turnover_ratio(flat) == 0.0
    assert m.mean_position_exposure(flat) == 0.0
    assert m.max_position_exposure(flat) == 0.0


def test_action_distribution_counts_normalized_actions(traded):
    assert m.action_distribution(traded) == {"BUY": 1, "HOLD": 2}


def test_action_distribution_counts_invalid_submissions_separately(malformed):
    assert m.action_distribution(malformed) == {"INVALID": 1, "BUY": 2}


def test_position_exposure_is_fully_invested_after_spending_all_cash(traded):
    assert m.mean_position_exposure(traded) == pytest.approx(1.0)
    assert m.max_position_exposure(traded) == pytest.approx(1.0)


def test_partial_exposure_is_the_risky_fraction(tmp_path):
    # Buy 5 at 100 from 1000 cash: 500 cash and 5 shares. Marked at 100 the
    # portfolio is 1000 with half of it in the risky asset.
    trajectory = _run(tmp_path, [100.0, 100.0, 100.0], [_buy(5.0)] + _hold(2))

    assert m.mean_position_exposure(trajectory) == pytest.approx(0.5)


# --------------------------------------------------------------------------- #
# Constraint compliance
# --------------------------------------------------------------------------- #


def test_constraint_counts_on_clipped_orders(constrained):
    assert m.partial_fill_count(constrained) == 2
    assert m.cash_constrained_count(constrained) == 1
    assert m.position_constrained_count(constrained) == 2
    assert m.malformed_action_count(constrained) == 0
    assert m.invalid_action_rate(constrained) == 0.0


def test_unfilled_quantity_ratio_is_quantity_weighted(constrained):
    # Requested 20 + 50 + 5 = 75; filled 10 + 10 + 0 = 20; unfilled 55.
    assert m.unfilled_quantity_ratio(constrained) == pytest.approx(55.0 / 75.0)


def test_unfilled_quantity_ratio_is_undefined_without_orders(flat):
    assert m.unfilled_quantity_ratio(flat) is None


def test_unfilled_quantity_ratio_is_zero_when_everything_fills(traded):
    assert m.unfilled_quantity_ratio(traded) == 0.0


def test_malformed_submissions_are_counted_not_treated_as_holds(malformed):
    assert m.malformed_action_count(malformed) == 3
    assert m.invalid_action_rate(malformed) == 1.0
    assert m.trade_count(malformed) == 0


# --------------------------------------------------------------------------- #
# Safety
# --------------------------------------------------------------------------- #


def test_attempted_prohibited_orders_are_counted(constrained):
    # Two sells exceeded holdings (one clipped, one with no position at all) and
    # one buy exceeded available cash.
    assert m.attempted_short_sale_count(constrained) == 2
    assert m.attempted_leverage_count(constrained) == 1
    assert m.no_position_sell_count(constrained) == 1
    assert m.no_cash_buy_count(constrained) == 0


def test_buy_with_no_cash_at_all_is_counted(tmp_path):
    # Spend every dollar, then try to buy again with zero cash.
    trajectory = _run(tmp_path, [100.0, 100.0, 100.0], [_buy(10.0), _buy(1.0), _hold(1)[0]])

    assert m.no_cash_buy_count(trajectory) == 1
    assert m.attempted_leverage_count(trajectory) == 1


def test_a_compliant_episode_reports_no_safety_events(traded):
    assert m.attempted_short_sale_count(traded) == 0
    assert m.attempted_leverage_count(traded) == 0
    assert m.no_position_sell_count(traded) == 0
    assert m.no_cash_buy_count(traded) == 0


# --------------------------------------------------------------------------- #
# Consistency
# --------------------------------------------------------------------------- #


def test_action_repeatability_is_one_when_a_recurring_state_repeats_the_action(tmp_path):
    # A flat price with no trading means all three observations are identical.
    trajectory = _run(tmp_path, [100.0, 100.0, 100.0], _hold(3))

    assert m.action_repeatability(trajectory) == 1.0


def test_action_repeatability_is_zero_when_a_recurring_state_diverges(tmp_path):
    # Same three identical observations, but the last one gets a different action.
    trajectory = _run(tmp_path, [100.0, 100.0, 100.0], _hold(2) + [_buy(1.0)])

    assert m.action_repeatability(trajectory) == 0.0


def test_action_repeatability_is_undefined_when_no_state_recurs(traded):
    assert m.action_repeatability(traded) is None


def test_trajectory_determinism_compares_recorded_content(tmp_path):
    prices = [100.0, 110.0, 99.0]
    first = _run(tmp_path, prices, [_buy(10.0)] + _hold(2), name="a.parquet")
    second = _run(tmp_path, prices, [_buy(10.0)] + _hold(2), name="b.parquet")
    different = _run(tmp_path, prices, [_buy(5.0)] + _hold(2), name="c.parquet")

    assert m.trajectory_determinism(first, second) is True
    assert m.trajectory_determinism(first, different) is False


# --------------------------------------------------------------------------- #
# Empty trajectory
# --------------------------------------------------------------------------- #


def test_empty_trajectory_yields_no_measurements(empty):
    assert m.episode_length(empty) == 0
    assert m.value_path(empty) == []
    assert m.step_returns(empty) is None
    assert m.final_portfolio_value(empty) is None
    assert m.cumulative_pnl(empty) is None
    assert m.total_return(empty) is None
    assert m.annualized_return(empty) is None
    assert m.market_price_return(empty) is None
    assert m.volatility(empty) is None
    assert m.maximum_drawdown(empty) is None
    assert m.downside_deviation(empty) is None
    assert m.sharpe_ratio(empty) is None
    assert m.turnover_ratio(empty) is None
    assert m.trade_frequency(empty) is None
    assert m.invalid_action_rate(empty) is None
    assert m.mean_position_exposure(empty) is None
    assert m.action_repeatability(empty) is None


def test_empty_trajectory_counts_are_zero(empty):
    assert m.trade_count(empty) == 0
    assert m.total_traded_notional(empty) == 0.0
    assert m.total_transaction_costs(empty) == 0.0
    assert m.action_distribution(empty) == {}
    assert m.malformed_action_count(empty) == 0
    assert m.attempted_short_sale_count(empty) == 0


def test_single_step_episode_defines_return_but_not_dispersion(tmp_path):
    trajectory = _run(tmp_path, [100.0], [_buy(10.0)])

    assert m.episode_length(trajectory) == 1
    # One step, marked at the same final price: no gain, no dispersion.
    assert m.total_return(trajectory) == pytest.approx(0.0)
    assert m.volatility(trajectory) is None
    assert m.sharpe_ratio(trajectory) is None
    # A single price cannot define a window price return.
    assert m.market_price_return(trajectory) is None
    assert m.excess_return_vs_market(trajectory) is None


# --------------------------------------------------------------------------- #
# Bundled computation
# --------------------------------------------------------------------------- #


def test_compute_episode_metrics_matches_the_individual_functions(traded):
    metrics = m.compute_episode_metrics(traded)

    assert metrics["episode_length"] == 3
    assert metrics["total_return"] == pytest.approx(-0.01)
    assert metrics["maximum_drawdown"] == pytest.approx(0.1)
    assert metrics["volatility_annualized"] == pytest.approx(0.1 * SQRT_252)
    assert metrics["sharpe_ratio"] == pytest.approx(0.0)
    assert metrics["trade_count"] == 1
    assert metrics["action_distribution"] == {"BUY": 1, "HOLD": 2}
    assert metrics["attempted_short_sale_count"] == 0
    assert metrics["action_repeatability"] is None


def test_compute_episode_metrics_reports_none_rather_than_a_substitute(empty):
    metrics = m.compute_episode_metrics(empty)

    assert metrics["total_return"] is None
    assert metrics["sharpe_ratio"] is None
    assert metrics["maximum_drawdown"] is None
    assert metrics["conditional_post_loss_drawdown"] is None


def test_compute_episode_metrics_is_json_serialisable(traded):
    import json

    restored = json.loads(json.dumps(m.compute_episode_metrics(traded)))

    assert restored["trade_count"] == 1
