# E5A Consolidated Multi-Window Analysis (STOP before ML)

**Windows (identical machinery, persistence, PIT rules, fingerprints):**

| window | experiment_id | grid | sessions | attribution fingerprint | repro |
|---|---|---|---|---|---|
| E5A-1 | E5A-deterministic-attribution-20260926 | 2023-05-15 → 2023-06-15 | 24 | 14ce55e5… | identical rerun |
| E5A-2 | E5A-window2-20260926 | 2023-06-16 → 2023-07-14 | 20 | a271d489… | identical rerun |
| E5A-3 | E5A-window3-20260926 | 2023-07-17 → 2023-08-14 | 21 | f089b153… | identical rerun |
| E5A-HV | E5A-highvix-20260926 | 2020-03-17 → 2020-04-15 | 18 | 5e545cf5… | identical rerun |

**High-VIX selection rule (declared before any outcome inspection):**
30-calendar-day window maximising mean VIX close, subject to ≥15 NSE grid
sessions, ≥90% RELIANCE/TCS exact-bar coverage, full data coverage, and
non-overlap with E5A-1/2/3. Mechanical winner: 2020-03-17→2020-04-15
(mean VIX 63.77, max 83.6, 18 sessions, 100% coverage). No window was
moved for SELL coverage (per constraint SELL is an observed property).

Per-window conditioning: `data/frozen_traces/_conditioning/*.json`
(read-only tool: `evaluation/attribution/conditioning.py`).
Combined dataset: `data/frozen_traces/_ml/e5a_combined_v1.json`
(sole loader: `evaluation/attribution/features.py:build_ml_dataset`).

---

## A. Does the original deterministic NULL persist? YES

Pre-trend_3d × adverse_MAE (populated denominators), per window:

| window | negative | flat | positive |
|---|---|---|---|
| E5A-1 | 2/8 = 0.25 | 9/14 = 0.64 | 3/6 = 0.50 |
| E5A-2 | 0/6 = 0.00 | 4/7 = 0.57 | 5/11 = 0.45 |
| E5A-3 | 6/10 = 0.60 | 7/11 = 0.64 | 4/5 = 0.80 |

Combined (N=106 populated): negative 8/24 = 0.33, flat 20/32 = 0.62,
positive 12/22 = 0.55; forward_3d: negative 2/22 = 0.09, flat 7/30 = 0.23,
positive 5/20 = 0.25. The "persistent negative trend + BUY → adverse"
pattern is absent in all three windows — negative-trend rows adverse
*least* often. No deterministic rule meets the validity criteria.
**B1 deterministic baseline remains NULL.**

## B. Any deterministic condition generalising across windows? NO

VIX terciles, exposure terciles (= temporal thirds, confounded),
instrument splits show no stable direction. E5A-3 has a markedly higher
MAE-adverse base rate (0.735 vs 0.500/0.417) with no trend/VIX/exposure
structure explaining it — heterogeneity without an attributable handle.

## C. Regime diversity: POOR

All training windows VIX 10.13–13.29 (LOW regime, narrow). E5A-HV
(VIX 49.7–83.6, all sessions > 25) produced **18/18 NO_ORDERS, 0
executions**: the benchmark never accumulates in sustained HIGH-VIX
(VIX never < 15 → no BUY; nothing held → no SELL). Informative about
participation, contributes zero training rows.

## D–F. Counts

- Executed: **106** (E5A-1: 36, E5A-2: 36, E5A-3: 34). NOOP/BLOCKED rows
  preserved but excluded from training.
- BUY **106**, SELL **0** — SELL coverage unobtainable without changing
  the frozen agent; not pursued.
- adverse_MAE **58/106 = 0.547**; adverse_forward_3d **28/100 = 0.280**
  (6 missing forward legs: window-edge + 2023-06-29 OPEN-session equity
  data gap — calendar VERIFIED HOLIDAY 06-28 adjacent; engine recorded
  None honestly, environment blocked 06-29 fills with NOOP_NO_PRICE).

## G. Feature variability

Sufficient: cash 0–100k, exposure 0–1, pre-trends span ±3%, avg_cost and
PnLs vary. WEAK: VIX (10–13.3, near-constant — uninformative as a model
input on this data); pre_trend_5d missing 40/106; position/avg_cost
missing 6/106 (pre-first-fill, encode as 0/None at model time).

## H. Temporal separation: WEAK

Three contiguous May→Aug 2023 windows, one regime. Mechanical
TRAIN(E5A-1)/VALID(E5A-2)/TEST(E5A-3) splits are possible but are
same-regime splits — they cannot support generalisation claims.

## I. Is ML scientifically justified? NOT YET (conditional pilot only)

A generalisable diagnostic model is not supportable: BUY-only, one
regime, N=106, NULL deterministic structure, weak temporal separation.
At most, a strictly-scoped BUY-only logistic-regression pilot on the
frozen feature set may be run as a calibration exercise — with the
positive result pre-registered as *non-generalisable* unless later
windows add regime diversity. No tree-based model (insufficient N and
diversity). Any M1 pilot that fails to beat prevalence is a null to be
reported, not tuned.

## J. Frozen ML target/feature set (for IF/when a pilot is approved)

- Target (primary): `adverse_mae`; secondary: `adverse_forward_3d`.
- Features (frozen allowlist, `features.py:DECISION_TIME_FEATURES`):
  pre_trend_1d/3d/5d, vix_tm1, cash_before, position_qty,
  exposure_before, avg_cost, realized/unrealized_pnl_before,
  total_equity_before, instrument, action, quantity.
- Outcomes (`RETROSPECTIVE_OUTCOMES`) structurally blocked from inputs;
  missing legs never imputed.

## K. Frozen temporal split (for IF/when)

TRAIN = E5A-1 (36) → VALID = E5A-2 (36) → TEST = E5A-3 (34).
E5A-HV excluded (no rows). Never shuffled. Permutation null required.

## L. Deterministic baseline ML must beat

B0 prevalence: P(adverse_mae) = 0.547, P(adverse_fwd3d) = 0.280.
B1 deterministic rule: NULL — ML must beat calibrated prevalence on the
held-out window. Calibration (Brier/log-loss/reliability) is the metric;
accuracy never central.

---

**No model trained. No repair hypothesis created** (window-3's elevated
base rate is an interesting heterogeneity, not an attributable pattern —
per constraint §11, no hypothesis is manufactured from it). Agent,
TargetObservation, MemoryStore, validation/admission untouched.
Awaiting review before any ML pilot.
