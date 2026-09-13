# Multi-Asset Indian Research Environment — Architecture Note

```
Canonical Data
      ↓
InformationSet (vintage assets: CPI / IIP / policy)
      ↓
Temporal Eligibility (strict PIT at caller-supplied decision timestamps)
      ↓
Multi-Asset Information Lookup (environment/indian/information_lookup.py)
      ↓
Environment State (typed market / macro / portfolio blocks + reasons)
      ↓
Action (validated order list, tradables only)
      ↓
Execution (next-session close, deterministic, reason-coded)
      ↓
Portfolio Accounting (cash + per-instrument avg-cost ledger)
      ↓
Reward (portfolio-value change incl. costs; nothing risk-adjusted)
```

Status: environment milestone. No agent, evaluator, diagnosis, repair,
scoring, or optimization logic lives here.

## Why publication assets are not market-session assets

CPI, IIP, policy events, G-Sec/T-bill weeks, Brent, and USD/INR (by
explicit decision: the RBI_FX Mumbai-holiday map is unacquired) carry
`requires_calendar=False`. A CPI + NSE experiment is therefore never
rejected for a missing MOSPI calendar row. Exchange-traded assets keep
`requires_calendar=True` and fail closed on UNKNOWN/CLOSED sessions.
Venue isolation holds throughout: NSE evidence never resolves MCX dates.

## Why availability is not observation time

CPI observation month ≠ release date; IIP observation month ≠
release/vintage date; policy announcement ≠ effective date. Lookup path
`vintage_pit` gates strictly on `availability_date <= decision_timestamp`.
Market CSVs carry no usable availability column, so path
`observation_lag` exposes only bars strictly before the decision date
under an explicit ≥1-day publication-lag assumption. Brent (100% NULL
availability) stays invisible under strict PIT. Again: no T+1, close, or
13:30 timestamp is fabricated anywhere.

## Why vintage is not observation time

`InformationSet` selects the latest eligible vintage upstream; the
environment consumes its result and labels the slot with vintage +
availability. Multi-vintage ambiguity without an explicit policy raises
instead of guessing (see `availability_policy`).

## Why calendar eligibility is not information eligibility

An OPEN session does not make information available (Brent on an NSE
trading day is still INFO_UNAVAILABLE), and available information does
not open a market (CPI release day can be CAL_CLOSED for NSE). The two
gates are evaluated independently and reported independently.

## Why missingness is not zero

Every slot carries AVAILABLE | OBS_MISSING | INFO_UNAVAILABLE |
CAL_UNKNOWN | CAL_CLOSED | CONSTRAINT_FAIL with asset, dates, vintage,
venue, and reason. Absent bars reject orders (NOOP_NO_PRICE); absent
marks contribute 0 to holdings value while listed as unpriced.

## Why forward-filling unavailable information is prohibited

Filling would present `availability > decision_timestamp` values to the
agent — look-ahead by construction. The lookup has no fill path; the
no-look-ahead suite (`tests/indian/test_no_lookahead.py`) proves
invisibility of future/NULL-availability rows, including through reward
and validation paths.

## Execution model (explicit)

Decide at session `t` on bars through `t−1` close; execute at `t`'s close
(or next eligible session); mark on visible closes; terminal row fills at
the final close. No `close_t == available_at_t == executable_at_t`
assumption. MCX sessions are UNKNOWN by evidence shortage, so gold
orders currently resolve NOOP_UNKNOWN_CALENDAR — an honest block, to be
lifted only by acquiring the MCX holiday map, never by inference.

## Determinism

Fixed config + fixed canonical files ⇒ identical grid, slots, fills, and
`market_fingerprint` (SHA-256 over grid dates and universe closes).
`spec()` records everything needed to reconstruct an episode.
