# Phase 1 Audit and Freeze

## Status

Phase 1 is READY for the next milestone: Static Evaluation Pipeline.

The current foundation can execute a deterministic trading episode using the
financial environment and a deterministic synthetic Agent Under Evaluation.

## Implemented and Tested

- Historical SPY/^VIX replay from processed parquet splits.
- Portfolio accounting for buy, sell, hold, insufficient cash, unavailable
  holdings, transaction costs, and no-op invalid trades.
- Stable observation contract with `date`, `market_price`, `vix`, and
  `portfolio` at the top level. The original nested `market_data` object is
  retained for compatibility.
- Agent reset contract for episode-local state.
- Deterministic synthetic agents and a placeholder deterministic LLM-agent
  abstraction.
- Complete end-to-end episode smoke test.
- Trace persistence to JSON and parquet.
- Pydantic schema JSON serialization smoke tests.

## Environment Contract

At each non-terminal timestep, the agent receives:

- `date`: current timestamp as `YYYY-MM-DD`.
- `market_price`: current SPY adjusted close used as the execution price.
- `vix`: current VIX value.
- `market_data`: raw market observation containing the same market fields.
- `portfolio.cash`: current cash.
- `portfolio.holdings`: current number of SPY shares.
- `portfolio.total_value`: cash plus holdings valued at current price.

The environment accepts:

- `BUY`
- `SELL`
- `HOLD`

Invalid actions, non-positive quantities, and non-positive execution prices are
treated as no-op trades.

## Information Boundary

The agent observes only the current timestep's date, SPY price, VIX value, and
portfolio state. It does not receive next-step price, next-step return, future
VIX, future reward, future drawdown, future market regime, or holdout labels.

Step outcome is calculated only after the action is submitted and the market is
advanced.

## Market Data Audit

Processed market splits under `data/processed/market_splits/` contain SPY and
^VIX columns. During the audit, all four existing splits were checked for:

- monotonic increasing timestamps;
- duplicate timestamps;
- missing values;
- non-positive prices/values.

No issues were found in the processed splits.

The `HistoricalMarket` loader now rejects empty data, missing required columns,
duplicate timestamps, unsorted timestamps, missing SPY/^VIX values, and
non-positive SPY/^VIX values.

## Reproducibility

Run project tests:

```bash
./.venv/bin/pytest -q
```

A deterministic smoke run over `data/processed/market_splits/discovery.parquet`
was executed three times with `FlawlessControlAgent`; all trajectories matched.

## Known Limitations

- The market currently models only one tradable asset, SPY, with VIX as an
  observable risk indicator.
- Execution occurs at adjusted close with no intraday order book, liquidity, or
  slippage model.
- Invalid trades are no-ops rather than exceptions.
- Insufficient cash buys execute the maximum affordable fractional quantity.
- Short selling and leverage are not implemented.
- The LLM trading agent is a deterministic placeholder and does not call an LLM.
- Static evaluation, adaptive evaluation, diagnosis, repair, and validation
  modules exist in the repository, but this audit freezes only the Phase 1
  financial-agent and financial-environment foundation.
