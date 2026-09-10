# Indian Data Contract V1.0

This contract defines the additive Indian data foundation. It does not change
the existing `HistoricalMarket` environment or Phase 3 adaptive evaluation
logic, and it does not define final experiment dates.

## Tiers

- **Tier A — tradable/state assets:** NSE equities and indices, government
  security/T-Bill state, USD/INR, and contract-level MCX gold.
- **Tier B — market state:** India VIX, sector indices, breadth, liquidity and
  trading activity.
- **Tier C — exogenous context:** RBI policy events, CPI, IIP, and crude oil.

## Required temporal semantics

Market records use their native observation/trade timestamp. Macro and policy
records carry both:

```text
observation_date   the period or effective date described by the value
availability_date  the first date the value could be known by the agent
```

`availability_date` must not precede `observation_date` in the V1 schemas.
Revisions retain a `revision_version`; a revised value must not replace an
earlier vintage in the agent information set unless its availability date has
arrived.

An alignment layer may expose a value on a later trading day only when
`availability_date <= simulated_timestamp`. It must preserve native
frequency first and must not blindly forward-fill prices, monthly releases,
auction observations, or policy events.

## Identifiers and price policy

Security-level equity data preserves symbol, ISIN, series, and security code
when available. `adjusted_close` is optional and must be sourced or explicitly
constructed under a documented corporate-action policy; it is never silently
manufactured. Unadjusted OHLC and action metadata remain available for audit.

Gold data is contract-level. Contract symbol, expiry, trade date, OHLC,
settlement, open interest, volume, and turnover are retained. No continuous
series is created in this milestone. A later roll method must be reproducible,
use only information available at the roll decision time, and be separately
leakage-audited.

## Raw and processed artifacts

Raw files under `data/raw/india/` are immutable evidence and are never
overwritten by normalization. Processed files under `data/processed/india/`
must have a separate path, processing version, parameters, and SHA-256 in the
dataset manifest. Pending or failed acquisition is represented in a manifest;
empty placeholder files are not valid data.

## Validation

The reusable coverage auditor reports individual temporal coverage, duplicates,
required-field missingness, frequency/gap checks, calendar consistency, and
availability-date violations. The common intersection is calculated from
audited artifacts and is evidence for a later methodological decision, not an
experiment split.

The leakage auditor checks future-derived columns, pre-release macro values,
split overlap, gold roll construction, and corporate-action timing. Any
unresolved information boundary blocks downstream use until resolved.
