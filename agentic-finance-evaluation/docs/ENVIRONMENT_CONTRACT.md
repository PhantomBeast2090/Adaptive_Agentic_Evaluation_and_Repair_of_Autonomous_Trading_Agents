# Frozen Financial Environment Contract

## Status

Phase 1.5 is complete. This contract is the stable boundary for building the
Phase 2 Static Evaluation Pipeline.

## Observation

Each active observation is a dictionary with:

- `date`: `YYYY-MM-DD` string for the current market row.
- `market_price`: SPY adjusted close as a float.
- `vix`: VIX value as a float.
- `market_data`: nested copy of the current market fields for compatibility.
- `portfolio.cash`: available cash as a float.
- `portfolio.holdings`: SPY share quantity as a float.
- `portfolio.total_value`: `cash + holdings * market_price`.

The observation contains current-timestep information only.

## Action

The environment accepts an action string and quantity:

- `BUY`: buy SPY shares.
- `SELL`: sell SPY shares.
- `HOLD`: no trade.

`quantity` is a non-negative float share quantity. Fractional quantities are
supported. Zero or negative quantities are deterministic no-ops.

There is no symbol field in Phase 1.5; SPY is the only tradable asset.

## Execution

Actions execute immediately at the current observation's `market_price`.

Oversized orders use deterministic partial-fill semantics:

- Oversized `BUY`: reduced to the maximum affordable fractional quantity after
  transaction costs.
- Oversized `SELL`: reduced to currently available holdings.

Invalid actions are no-ops. Short selling, leverage, slippage, and liquidity
constraints are not implemented.

## Costs

Transaction costs are configured in basis points.

- Buy fee: `quantity * price * transaction_cost_bps / 10000`.
- Sell fee: `quantity * price * transaction_cost_bps / 10000`.

Fees are applied exactly once per executed trade. `HOLD`, invalid actions, and
non-positive quantities incur no fee.

## Reward and Portfolio State

Before each action, the environment values the portfolio at the current price.
After execution:

- On non-final rows, the market advances one row and portfolio value is marked
  at the next row's price.
- On the final row, no future price exists, so portfolio value is marked at the
  same final-row execution price.

`step_pnl` is post-step portfolio value minus pre-action portfolio value.
`cumulative_pnl` is post-step portfolio value minus initial cash.
`drawdown` is measured from the episode peak portfolio value.

Each outcome includes:

- `step_pnl`
- `cumulative_pnl`
- `drawdown`
- `transaction_costs`
- `execution_price`
- `portfolio_value`
- `cash`
- `holdings`
- `date`

## Termination

The environment permits one action for every market row, including the final
row. The final-row action executes at the final current price, returns the final
observable portfolio state, and sets `done=True` with
`reason="market_exhausted"`.

Calling `step()` again after termination is a deterministic no-op that returns
the final observable state, `done=True`, and `reason="episode_already_done"`.

`reset()` starts a fresh episode, resets market position, portfolio state, peak
value, and done state.

## Information Boundary

At timestep `t`, the agent receives only current date, current SPY price,
current VIX, and current portfolio state.

The agent does not receive:

- future prices;
- future returns;
- future rewards;
- future portfolio values;
- future VIX;
- future market regimes;
- holdout labels.

Step outcome is generated only after an action is submitted.

## Determinism

The Phase 1.5 environment is deterministic for fixed:

- market parquet file;
- initial cash;
- transaction-cost configuration;
- deterministic agent state.

The current test suite verifies repeated identical trajectories for the same
controlled input.
