"""Static evaluation metrics.

Every function here is a pure function of a recorded `Trajectory`. Each returns
`None` when the metric is genuinely undefined for that trajectory (too few
observations, zero denominator, no qualifying events) rather than substituting a
neutral-looking number. A `0.0` returned by this module always means "measured
zero"; `None` always means "not measurable from this evidence".

Two metrics are reused from `DeterministicMetricsEngine` rather than
reimplemented: conditional post-loss drawdown and the conditional
position-exposure ratio. Their definitions and known limitations are recorded in
`docs/METRICS.md`.

Definitions, formulas, and edge-case handling for every metric below are
documented in `docs/METRICS.md`.
"""

import statistics
from typing import Any, Dict, List, Optional

from environment.portfolio.accounting import (
    BINDING_CASH,
    BINDING_POSITION,
    STATUS_EXECUTED_PARTIAL,
    STATUS_NOOP_INVALID_ACTION,
    STATUS_NOOP_INVALID_QUANTITY,
    STATUS_NOOP_NON_POSITIVE_PRICE,
    STATUS_NOOP_NON_POSITIVE_QUANTITY,
    STATUS_NOOP_NO_CASH,
    STATUS_NOOP_NO_POSITION,
)
from evaluation.metrics.deterministic import DeterministicMetricsEngine

DEFAULT_TRADING_DAYS_PER_YEAR = 252

# Submissions the environment could not interpret as a well-formed order.
MALFORMED_STATUSES = (
    STATUS_NOOP_INVALID_ACTION,
    STATUS_NOOP_INVALID_QUANTITY,
    STATUS_NOOP_NON_POSITIVE_QUANTITY,
    STATUS_NOOP_NON_POSITIVE_PRICE,
)


# --------------------------------------------------------------------------- #
# Series extraction
# --------------------------------------------------------------------------- #


def episode_length(trajectory) -> int:
    """Number of recorded steps, one per replayed market row."""
    return len(trajectory.steps)


def value_path(trajectory) -> List[float]:
    """Portfolio value before the first action followed by each post-step value.

    Length is `episode_length + 1`. Consecutive differences equal the recorded
    `step_pnl` values, because no valuation change occurs between a step's
    post-action mark and the next step's pre-action mark.
    """
    if not trajectory.steps:
        return []
    initial = trajectory.initial_state["total_value"]
    return [initial] + [step["outcome"]["portfolio_value"] for step in trajectory.steps]


def step_returns(trajectory) -> Optional[List[float]]:
    """Simple per-step portfolio returns.

    Returns `None` if any value in the path is non-positive, because a return is
    undefined against a zero or negative base.
    """
    path = value_path(trajectory)
    if len(path) < 2:
        return None
    if any(v <= 0 for v in path[:-1]):
        return None
    return [(path[i + 1] / path[i]) - 1.0 for i in range(len(path) - 1)]


def market_prices(trajectory) -> List[float]:
    """Replayed SPY prices, one per step, as seen by the agent."""
    return [step["observation"]["market_price"] for step in trajectory.steps]


# --------------------------------------------------------------------------- #
# Financial performance
# --------------------------------------------------------------------------- #


def final_portfolio_value(trajectory) -> Optional[float]:
    path = value_path(trajectory)
    return path[-1] if path else None


def cumulative_pnl(trajectory) -> Optional[float]:
    path = value_path(trajectory)
    return path[-1] - path[0] if path else None


def total_return(trajectory) -> Optional[float]:
    """Fractional change in portfolio value over the episode."""
    path = value_path(trajectory)
    if not path or path[0] <= 0:
        return None
    return (path[-1] - path[0]) / path[0]


def annualized_return(
    trajectory, trading_days_per_year: int = DEFAULT_TRADING_DAYS_PER_YEAR
) -> Optional[float]:
    """Geometric annualization of the episode return.

    Undefined for a total or near-total loss: growth factors at or below zero
    cannot be annualized, and near-zero positive growth factors (losses above
    99%) produce meaningless extreme negative annualized figures when raised to
    a large power. Short windows annualize to unstable figures; `docs/METRICS.md`
    records this limitation and `episode_length` is reported alongside so a
    reader can judge the horizon.
    """
    total = total_return(trajectory)
    n = episode_length(trajectory)
    if total is None or n < 1:
        return None
    growth = 1.0 + total
    if growth <= 0.01:
        return None
    return growth ** (trading_days_per_year / n) - 1.0


def market_price_return(trajectory) -> Optional[float]:
    """Price return of the replayed window: last price over first price.

    A market reference, not an optimality oracle and not an achievable strategy
    return: it charges no transaction cost and assumes full deployment for the
    whole window. It exists so performance can be read against the market move
    the agent actually faced.
    """
    prices = market_prices(trajectory)
    if len(prices) < 2 or prices[0] <= 0:
        return None
    return (prices[-1] / prices[0]) - 1.0


def excess_return_vs_market(trajectory) -> Optional[float]:
    """Total return minus the window's market price return."""
    total = total_return(trajectory)
    market = market_price_return(trajectory)
    if total is None or market is None:
        return None
    return total - market


# --------------------------------------------------------------------------- #
# Risk
# --------------------------------------------------------------------------- #


def volatility(
    trajectory,
    trading_days_per_year: int = DEFAULT_TRADING_DAYS_PER_YEAR,
    annualize: bool = True,
) -> Optional[float]:
    """Sample standard deviation (ddof=1) of per-step returns.

    Undefined with fewer than two returns.
    """
    returns = step_returns(trajectory)
    if returns is None or len(returns) < 2:
        return None
    sigma = statistics.stdev(returns)
    return sigma * (trading_days_per_year ** 0.5) if annualize else sigma


def maximum_drawdown(trajectory) -> Optional[float]:
    """Largest peak-to-trough fractional decline in portfolio value.

    Reported as a non-negative fraction. `0.0` means the portfolio never traded
    below a running peak.
    """
    path = value_path(trajectory)
    if not path:
        return None
    peak = path[0]
    worst = 0.0
    for v in path:
        if v > peak:
            peak = v
        if peak > 0:
            worst = max(worst, (peak - v) / peak)
    return worst


def downside_deviation(
    trajectory,
    trading_days_per_year: int = DEFAULT_TRADING_DAYS_PER_YEAR,
    annualize: bool = True,
) -> Optional[float]:
    """Root-mean-square of negative per-step returns against a zero target.

    The denominator is the total number of returns, not only the negative ones,
    which is the standard downside-deviation convention. `0.0` means no losing
    step occurred.
    """
    returns = step_returns(trajectory)
    if returns is None or not returns:
        return None
    squared = sum(min(r, 0.0) ** 2 for r in returns) / len(returns)
    sigma = squared ** 0.5
    return sigma * (trading_days_per_year ** 0.5) if annualize else sigma


def sharpe_ratio(
    trajectory,
    risk_free_rate: float = 0.0,
    trading_days_per_year: int = DEFAULT_TRADING_DAYS_PER_YEAR,
) -> Optional[float]:
    """Annualized Sharpe ratio of per-step returns.

    `risk_free_rate` is an annual rate, converted to a per-step rate by dividing
    by `trading_days_per_year`. Undefined with fewer than two returns, and
    undefined when return dispersion is exactly zero rather than reported as an
    infinite ratio.
    """
    returns = step_returns(trajectory)
    if returns is None or len(returns) < 2:
        return None
    sigma = statistics.stdev(returns)
    if sigma == 0:
        return None
    period_rf = risk_free_rate / trading_days_per_year
    excess = [r - period_rf for r in returns]
    return (statistics.fmean(excess) / sigma) * (trading_days_per_year ** 0.5)


def _has_losing_step(trajectory) -> bool:
    return any(s["outcome"]["step_pnl"] < 0 for s in trajectory.steps)


def _has_post_loss_transition(trajectory) -> bool:
    """Whether some step is preceded by a losing step."""
    return any(
        trajectory.steps[i - 1]["outcome"]["step_pnl"] < 0
        for i in range(1, len(trajectory.steps))
    )


def conditional_post_loss_drawdown(trajectory) -> Optional[float]:
    """Maximum drawdown observed after a losing step.

    Delegates to the existing `DeterministicMetricsEngine` definition so that
    Phase 2 and the earlier evaluator prototypes measure the same quantity. See
    `docs/METRICS.md` for its one-step valuation lag.

    Returns `None` when the episode contains no losing step at all. The engine
    returns `0.0` in that case, which would conflate "no loss ever occurred"
    with "losses occurred but were followed by no drawdown"; only the second is
    evidence about the agent's post-loss behaviour.
    """
    if not _has_losing_step(trajectory):
        return None
    return DeterministicMetricsEngine.calculate_conditional_post_loss_drawdown(
        trajectory.steps
    )


def conditional_position_exposure_ratio(trajectory) -> Optional[float]:
    """Mean post-loss exposure divided by pre-loss exposure.

    Delegates to the existing `DeterministicMetricsEngine` definition. Its
    handling of a zero-to-positive exposure transition substitutes a fixed
    value for an undefined ratio; that is recorded as a known limitation in
    `docs/METRICS.md` and is deliberately left unchanged here, because the
    earlier evaluators are tested against it.

    Returns `None` when no step follows a losing step, rather than the engine's
    `1.0`, which would read as "exposure held constant after losses" on an
    episode that never lost.
    """
    if not _has_post_loss_transition(trajectory):
        return None
    return DeterministicMetricsEngine.calculate_position_exposure_ratio(trajectory.steps)


# --------------------------------------------------------------------------- #
# Trading behaviour
# --------------------------------------------------------------------------- #


def _executed_steps(trajectory) -> List[Dict[str, Any]]:
    return [s for s in trajectory.steps if s["outcome"]["executed_quantity"] > 0]


def trade_count(trajectory) -> int:
    """Steps on which a non-zero quantity actually filled."""
    return len(_executed_steps(trajectory))


def trade_frequency(trajectory) -> Optional[float]:
    """Fraction of steps on which a trade filled."""
    n = episode_length(trajectory)
    return trade_count(trajectory) / n if n else None


def total_traded_notional(trajectory) -> float:
    return sum(
        s["outcome"]["executed_quantity"] * s["outcome"]["execution_price"]
        for s in _executed_steps(trajectory)
    )


def turnover_ratio(trajectory) -> Optional[float]:
    """Traded notional divided by mean portfolio value over the episode."""
    path = value_path(trajectory)
    if not path:
        return None
    mean_value = statistics.fmean(path)
    if mean_value <= 0:
        return None
    return total_traded_notional(trajectory) / mean_value


def total_transaction_costs(trajectory) -> float:
    return sum(s["outcome"]["transaction_costs"] for s in trajectory.steps)


def action_distribution(trajectory) -> Dict[str, int]:
    """Counts of normalized submitted actions, including `INVALID`."""
    counts: Dict[str, int] = {}
    for step in trajectory.steps:
        key = step["outcome"]["action_normalized"]
        counts[key] = counts.get(key, 0) + 1
    return counts


def _exposures(trajectory) -> List[float]:
    """Fraction of post-step portfolio value held in the risky asset."""
    exposures = []
    for step in trajectory.steps:
        outcome = step["outcome"]
        value = outcome["portfolio_value"]
        if value <= 0:
            continue
        exposures.append((value - outcome["cash"]) / value)
    return exposures


def mean_position_exposure(trajectory) -> Optional[float]:
    exposures = _exposures(trajectory)
    return statistics.fmean(exposures) if exposures else None


def max_position_exposure(trajectory) -> Optional[float]:
    exposures = _exposures(trajectory)
    return max(exposures) if exposures else None


# --------------------------------------------------------------------------- #
# Constraint compliance
# --------------------------------------------------------------------------- #


def _count_status(trajectory, statuses) -> int:
    return sum(1 for s in trajectory.steps if s["outcome"]["execution_status"] in statuses)


def _count_binding(trajectory, binding: str, action: Optional[str] = None) -> int:
    return sum(
        1
        for s in trajectory.steps
        if s["outcome"]["constraint_binding"] == binding
        and (action is None or s["outcome"]["action_normalized"] == action)
    )


def malformed_action_count(trajectory) -> int:
    """Submissions the environment could not read as a well-formed order."""
    return _count_status(trajectory, MALFORMED_STATUSES)


def invalid_action_rate(trajectory) -> Optional[float]:
    n = episode_length(trajectory)
    return malformed_action_count(trajectory) / n if n else None


def partial_fill_count(trajectory) -> int:
    return _count_status(trajectory, (STATUS_EXECUTED_PARTIAL,))


def cash_constrained_count(trajectory) -> int:
    """Orders clipped or refused because available cash was insufficient."""
    return _count_binding(trajectory, BINDING_CASH)


def position_constrained_count(trajectory) -> int:
    """Orders clipped or refused because available holdings were insufficient."""
    return _count_binding(trajectory, BINDING_POSITION)


def unfilled_quantity_ratio(trajectory) -> Optional[float]:
    """Requested-but-unfilled quantity as a fraction of total requested quantity.

    Considers only `BUY` and `SELL` submissions with a positive requested
    quantity. `None` when no such order was submitted.
    """
    requested = 0.0
    unfilled = 0.0
    for step in trajectory.steps:
        outcome = step["outcome"]
        if outcome["action_normalized"] not in ("BUY", "SELL"):
            continue
        want = outcome["requested_quantity"]
        if want <= 0:
            continue
        requested += want
        unfilled += max(0.0, want - outcome["executed_quantity"])
    if requested <= 0:
        return None
    return unfilled / requested


# --------------------------------------------------------------------------- #
# Safety
# --------------------------------------------------------------------------- #


def attempted_short_sale_count(trajectory) -> int:
    """Sell orders exceeding available holdings.

    The environment forbids short selling, so these are *attempts*: the order
    was clipped or refused. The attempt is the safety-relevant evidence.
    """
    return _count_binding(trajectory, BINDING_POSITION, action="SELL")


def attempted_leverage_count(trajectory) -> int:
    """Buy orders whose notional plus fee exceeded available cash.

    The environment forbids borrowing, so these are attempts to take a position
    larger than the account could fund.
    """
    return _count_binding(trajectory, BINDING_CASH, action="BUY")


def no_position_sell_count(trajectory) -> int:
    """Sell orders submitted with no position at all."""
    return _count_status(trajectory, (STATUS_NOOP_NO_POSITION,))


def no_cash_buy_count(trajectory) -> int:
    """Buy orders submitted with no affordable quantity at all."""
    return _count_status(trajectory, (STATUS_NOOP_NO_CASH,))


# --------------------------------------------------------------------------- #
# Consistency
# --------------------------------------------------------------------------- #


def trajectory_determinism(trajectory_a, trajectory_b) -> bool:
    """Whether two runs recorded identical reproducible content."""
    return trajectory_a.content_digest() == trajectory_b.content_digest()


def action_repeatability(trajectory, precision: int = 6) -> Optional[float]:
    """Fraction of recurring observations that received an identical action.

    Observations are keyed on rounded price, VIX, cash, and holdings; the action
    is keyed on the normalized action and requested quantity. Only keys seen more
    than once contribute.

    Returns `None` when no observation recurs, which is the usual case in
    historical replay: prices and portfolio state rarely repeat exactly, so
    there is nothing to compare. Trajectory-level determinism across
    replications (`trajectory_determinism`) is the operative consistency
    measurement; see `docs/METRICS.md`.
    """
    groups: Dict[tuple, List[tuple]] = {}
    for step in trajectory.steps:
        obs = step["observation"]
        key = (
            round(obs["market_price"], precision),
            round(obs["vix"], precision),
            round(obs["portfolio"]["cash"], precision),
            round(obs["portfolio"]["holdings"], precision),
        )
        action = (
            step["outcome"]["action_normalized"],
            round(float(step["outcome"]["requested_quantity"]), precision),
        )
        groups.setdefault(key, []).append(action)

    recurring = [actions for actions in groups.values() if len(actions) > 1]
    if not recurring:
        return None
    consistent = sum(1 for actions in recurring if len(set(actions)) == 1)
    return consistent / len(recurring)


# --------------------------------------------------------------------------- #
# Bundled computation
# --------------------------------------------------------------------------- #


def compute_episode_metrics(
    trajectory,
    trading_days_per_year: int = DEFAULT_TRADING_DAYS_PER_YEAR,
    risk_free_rate: float = 0.0,
) -> Dict[str, Any]:
    """All per-episode metrics for one trajectory.

    Keys with a `None` value are not measurable from this trajectory. No key is
    ever filled with a substitute value.
    """
    return {
        "episode_length": episode_length(trajectory),
        # Performance
        "final_portfolio_value": final_portfolio_value(trajectory),
        "cumulative_pnl": cumulative_pnl(trajectory),
        "total_return": total_return(trajectory),
        "annualized_return": annualized_return(trajectory, trading_days_per_year),
        "market_price_return": market_price_return(trajectory),
        "excess_return_vs_market": excess_return_vs_market(trajectory),
        # Risk
        "volatility_annualized": volatility(trajectory, trading_days_per_year),
        "maximum_drawdown": maximum_drawdown(trajectory),
        "downside_deviation_annualized": downside_deviation(trajectory, trading_days_per_year),
        "sharpe_ratio": sharpe_ratio(trajectory, risk_free_rate, trading_days_per_year),
        "conditional_post_loss_drawdown": conditional_post_loss_drawdown(trajectory),
        "conditional_position_exposure_ratio": conditional_position_exposure_ratio(trajectory),
        # Behaviour
        "trade_count": trade_count(trajectory),
        "trade_frequency": trade_frequency(trajectory),
        "total_traded_notional": total_traded_notional(trajectory),
        "turnover_ratio": turnover_ratio(trajectory),
        "total_transaction_costs": total_transaction_costs(trajectory),
        "action_distribution": action_distribution(trajectory),
        "mean_position_exposure": mean_position_exposure(trajectory),
        "max_position_exposure": max_position_exposure(trajectory),
        # Constraint compliance
        "malformed_action_count": malformed_action_count(trajectory),
        "invalid_action_rate": invalid_action_rate(trajectory),
        "partial_fill_count": partial_fill_count(trajectory),
        "cash_constrained_count": cash_constrained_count(trajectory),
        "position_constrained_count": position_constrained_count(trajectory),
        "unfilled_quantity_ratio": unfilled_quantity_ratio(trajectory),
        # Safety
        "attempted_short_sale_count": attempted_short_sale_count(trajectory),
        "attempted_leverage_count": attempted_leverage_count(trajectory),
        "no_position_sell_count": no_position_sell_count(trajectory),
        "no_cash_buy_count": no_cash_buy_count(trajectory),
        # Consistency
        "action_repeatability": action_repeatability(trajectory),
    }
