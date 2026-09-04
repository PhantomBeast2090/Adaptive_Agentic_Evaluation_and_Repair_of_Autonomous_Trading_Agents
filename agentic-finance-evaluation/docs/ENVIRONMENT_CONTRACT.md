# Frozen Financial Environment Contract

## Status

Phase 1.5 is complete. This contract is the stable boundary for building the
Phase 2 Static Evaluation Pipeline.

Phase 2 made two **additive** extensions, recorded in
"Phase 2 Additive Extensions" below. Execution economics — fill sizes, fees,
partial-fill rules, termination, and the information boundary — are unchanged.

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

---

## Phase 2 Additive Extensions

Two extensions were required before static evaluation could measure anything
beyond profit and loss. Both are additive: no existing field changed meaning and
no existing fill or fee arithmetic changed.

### 1. Episode windowing

`FinancialEnvironment` and `HistoricalMarket` accept optional `start_date` and
`end_date` arguments (`YYYY-MM-DD`).

- Bounds are **inclusive** on both ends.
- Bounds that fall on non-trading days clip to the available rows inside the
  range.
- Omitting both replays the whole file, exactly as before.
- A window that selects zero rows raises `ValueError`. It does not silently fall
  back to replaying the whole file.
- A window whose start is after its end raises `ValueError`.
- Data-quality validation runs on the **whole file** before slicing, so an
  invalid row outside the window is still rejected.

Windowing is what makes distinct static scenarios possible from one split file
without mutating or duplicating market data. Raw and processed data remain
immutable.

`HistoricalMarket.fingerprint()` returns a SHA-256 digest of the replayed
window's `(date, SPY, ^VIX)` rows. Two identical windows in different files
produce the same fingerprint; two different windows do not.

`FinancialEnvironment.spec()` returns the configuration needed to reconstruct
the environment: data path, requested and resolved window bounds, row count,
market fingerprint, initial cash, and transaction cost.

### 2. Execution reporting

Constraint compliance and safety cannot be measured from portfolio deltas alone:
a partially filled buy and a smaller fully filled buy leave identical portfolio
state. The environment therefore now reports what it did with each submitted
action.

`Portfolio.execute(action, quantity, price)` returns an `ExecutionReport`:

- `action_normalized`: `BUY`, `SELL`, `HOLD`, or `INVALID`;
- `requested_quantity`: what the agent asked for;
- `executed_quantity`: what the environment filled;
- `execution_price`;
- `transaction_cost`;
- `status` (exactly one per action, see below);
- `constraint_binding`: `cash`, `position`, or `None`.

`Portfolio.execute_trade(...)` is retained and still returns only the fee.

Status codes:

| Status | Meaning |
| --- | --- |
| `EXECUTED_FULL` | Filled at the requested quantity |
| `EXECUTED_PARTIAL` | Clipped by cash (buy) or holdings (sell) |
| `NOOP_HOLD` | `HOLD` submitted |
| `NOOP_INVALID_ACTION` | Action not in `{BUY, SELL, HOLD}`, or non-string |
| `NOOP_INVALID_QUANTITY` | Quantity not numeric |
| `NOOP_NON_POSITIVE_QUANTITY` | Quantity `<= 0` |
| `NOOP_NON_POSITIVE_PRICE` | Execution price `<= 0` |
| `NOOP_NO_CASH` | Buy with no affordable quantity |
| `NOOP_NO_POSITION` | Sell with no holdings |
| `NOOP_EPISODE_DONE` | Action submitted after termination |

Each step outcome dictionary gains `action_normalized`, `requested_quantity`,
`executed_quantity`, `execution_status`, and `constraint_binding`.

**One behavioural change:** a `BUY`/`SELL` with a non-numeric quantity
previously raised `TypeError`. It is now a reported no-op
(`NOOP_INVALID_QUANTITY`), consistent with the existing rule that malformed
submissions are no-ops rather than exceptions. This keeps a malformed agent
measurable instead of aborting an evaluation run. Cash, holdings, and fees are
unaffected.

### What these extensions deliberately do not add

- No short selling, leverage, slippage, liquidity, or market-impact model. The
  safety dimension measures *attempted* prohibited orders (a sell exceeding
  holdings, a buy exceeding cash) via `constraint_binding`; the environment
  still refuses to execute them.
- No new observation fields. The information boundary is unchanged: the agent
  still receives only current date, price, VIX, and portfolio state.

