---
name: indian-market-integrity
description: Enforce Indian-market rules: t-1 point-in-time visibility, vintage policies, venue calendars, NOOP honest blocks, Gold UNKNOWN-calendar handling, Brent invisibility, configured universe, manifest SHA-256 provenance. Invoke before touching environment, data, calendars, or configs. May consult S1 milestone-integrity.
---
---

# Indian Market Integrity

May consult `milestone-integrity` (S1) for freeze/change protocol. Owns no
change process and no evaluation-loop semantics.

## 1. Temporal core (point-in-time correctness)

- Decision at session `t` sees market information only through `t-1`
  (`environment/indian/information_lookup.py`, strict-`<` observation-lag path).
- Valid orders fill at `t` close (`environment/indian/environment.py`,
  `portfolio.py` execution-price path). No carry-forward.
- Same-bar `close/high/low` never enters agent state. Never recompute
  environment arithmetic in tests — assert against env-produced values.

## 2. Vintage semantics (`src/india/information_set.py`)

- `vintage_pit` path: latest eligible vintage with `availability <= t`.
- Policies: `explicit` / `earliest_available` / `latest_available`; unknown
  policy fails closed (`CONSTRAINT_FAIL`).
- `allow_pre_observation` exceptions exist (RBI policy announcements may precede
  effective dates); CPI/IIP are strict. Raw contract: `observation_date` vs
  `availability_date`, `revision_version`; `point_in_time_unverified` rows are
  ineligible (`INDIAN_DATA_CONTRACT.md`).

## 3. Venue calendars (no silent filling)

- Venue-isolated calendars (`src/india/historical_calendar.py`,
  `session_resolver.py`); master decision grid is NSE_CM (`clock.py`).
- `UNKNOWN` / `CONFLICT` fail closed. No cross-venue fallback, no inference,
  no interpolation. Never fill a missing bar with a substitute.

## 4. Honest-block taxonomy (findings, not errors to route around)

- Execution blocks: `NOOP_UNKNOWN_CALENDAR`, `NOOP_MARKET_CLOSED`,
  `NOOP_NO_PRICE`, `NOOP_UNKNOWN_ASSET`, `NON_TRADEABLE_ASSET`,
  `INSTRUMENT_OUTSIDE_UNIVERSE` (spelling preserved), plus legacy
  `NOOP_HOLD` / `INVALID_*` / `NO_CASH` / `NO_POSITION`.
- Slot statuses: `AVAILABLE`, `OBS_MISSING`, `INFO_UNAVAILABLE`, `CAL_UNKNOWN`,
  `CAL_CLOSED`, `CONSTRAINT_FAIL`.
- Doctrine: blocks are data to preserve and report, never obstacles to infer
  around. A blocked trade is a correct outcome.

## 5. Special cases

- **MCX Gold:** no acquired holiday map → sessions resolve `UNKNOWN` → orders
  honestly block as `NOOP_UNKNOWN_CALENDAR`. Liftable only by acquiring the
  map (`registry.py` keeps `requires_calendar=True`). Never by inference.
- **Brent:** 100% NULL availability → strict invisibility (`INFO_UNAVAILABLE`,
  zero agent-eligible rows). Never NSE-forced, never filled.

## 6. Universe and provenance

- Configured instrument universe is source of truth, never inferred or expanded
  (`environment.py` config path; `configs/indian_environment.yaml` shape).
- Per-dataset manifests with per-file raw SHA-256 + processed SHA-256
  (`src/india/manifest.py`; `data/manifests/india/*.yaml`). Processed never
  overwrites raw; placeholders forbidden.
- 14-dataset inventory (`INDIAN_DATA_SOURCE_INVENTORY.md`); `VALIDATED_BUT_BLOCKED`
  means usable only after calendar + experiment-intersection gates.

## 7. Enforcement map (tests that pin these rules)

`tests/india/test_*_canonical.py` (schema, dedup-identical-only, SHA
recomputation), `test_leakage.py`, `test_vintage_availability.py`,
`test_temporal_eligibility.py`, `test_information_set.py`,
`test_experiment_intersection.py`, `test_calendar_applicability.py`,
`tests/indian/test_no_lookahead.py`, `tests/baseline/test_leakage.py`.
If a change weakens any of these, stop and replan.

## 8. Maintenance

Update on dataset or semantics changes only; annual stale-review otherwise.
