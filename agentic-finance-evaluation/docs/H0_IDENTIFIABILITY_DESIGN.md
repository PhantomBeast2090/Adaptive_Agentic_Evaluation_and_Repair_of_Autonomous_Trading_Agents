# H0 Identifiability Design (DESIGN GATE — no implementation yet)

## Forensic findings

1. `MultiAssetPortfolio(initial_cash)` always starts empty
   (`environment/indian/portfolio.py:39-50`); no initial-positions
   path exists. BaselineConfig exposes `initial_cash` (default 100k).
2. `run_baseline(agent, config)` takes full config → multiple capitals
   against the same window needs only config variation. No runner
   change required.
3. Market observations are portfolio-independent by construction
   (observation-lag bars + portfolio snapshot); same date + same
   market data ⇒ identical market legs across branches. Pairing is
   structural, not arranged.
4. Agent policy (multi-asset v1.1) branches on cash (affordability,
   dust), exposure (brake/halt tiers), concentration (taper),
   drawdown (trim/flatten) — all capital-sensitive. Same-date action
   disagreement is mechanistically expected where tiers bite
   differently, without touching policy logic.

## Proposed state grid (pre-registered, outcome-blind)

initial_cash ∈ {25000, 50000, 100000, 200000} (0.25×/0.5×/1×/2×).
Rationale (arithmetic, not fitted): 25k forces dust/binding regimes;
50k binds affordability on expensive names; 100k reproduces F0R/G1;
200k reaches the 0.5 exposure brake. Window: 2020-01-01→2020-09-30
(G1-A equivalent: descent/crash/rebound in one trace).
Expected (not asserted): low-capital → q1/binding/pauses; high-capital
→ brake/taper/rotation; disagreement concentrated at tier crossings.

## Paired structure

Cluster = market date (189 sessions). Branches = 4 capitals.
Market legs identical by construction (§3 above); only
portfolio_before differs. Analysis is cluster-aware (paired
disagreement, cluster bootstrap); branches never counted as
independent market observations.

## Splits (pre-registered)

Temporal thirds of the window: TRAIN 2020-01-01→2020-03-31,
VALID 2020-04-01→2020-06-30, TEST 2020-07-01→2020-09-30.
Gate: ≥3 states executed; ≥2 actions; ≥2 quantities; ≥3 instruments;
≥15 paired-contrast obs (TRAIN); VALID≥10 / TEST≥20 labelled;
≥1 same-regime state-A/B action split repeated in TRAIN with
VALID+TEST support. Miner/thresholds unchanged if ever reached.

## Implementation plan (on approval)

`configs/choice_agent/h0_states.yaml`, `scripts/run_h0.py` (config
loop + fingerprinted `_h0/` persistence + spec JSON), 
`tests/agents/test_h0_branches.py` (14 focused areas; mutation tests
via synthetic failing-capital/market-shift fixtures), support audit,
verdict. No attribution/mining/repair in H0. No frozen touches.
