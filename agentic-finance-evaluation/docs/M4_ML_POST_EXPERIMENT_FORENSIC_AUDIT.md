# M4 — Post-ML Forensic Audit (2026-09-26)

## 1. Executive summary

Question: why did the ML extension (M1/M2b/M3/HGB, Chronos-2,
TimesFM-3, conditional miner) produce zero actionable hypotheses?

Evidence-backed answer: **primarily C (sample/regime) interacting
with G (miner thresholds), with B finding genuine but unstable
within-split information; D (target) is a confirmed secondary issue;
F (context/sequence) is the largest untested surface.** Concretely:

* Forecasts are healthy (106/106 AVAILABLE both models, real
  intervals, per-instrument and per-regime variation, deterministic).
* Tercile descriptives show within-split adverse-rate spreads on most
  features (e.g. Chronos TRAIN `f_interval_width_5d` low 0.77 vs high
  0.50; `f_ret_1d` 0.62 vs 0.33) — **information exists pre-mining**.
* The miner kills 948–949 of ~950 universe conditions at the N≥15
  gate (pairwise conjunctions on n=36 TRAIN); the 5 survivors die on
  Δ<0.02 or VALID non-confirmation. Near-miss `instrument=TCS:EQ`
  (TRAIN 0.556 vs 0.50) flips on VALID (0.389 vs 0.417).
* Spread directions flip across splits; Chronos↔TimesFM directional
  agreement is 53/106 (coin flip); prevalence swings 0.50→0.42→0.74.
* Targets disagree on 27% of labelled decisions, asymmetrically: all
  forward-adverse ⊆ MAE-adverse; 27 MAE-adverse decisions recovered by
  day 3.
* ML rows are point-in-time independent; trajectories contain unused
  sequential state (positions, exposure path, order history).

Verdict class: **CASE 6 leaning CASE 2/3** — the sample cannot cleanly
separate "no signal" from "signal the miner cannot express", but the
within-split spreads + VALID flips point to instability-first, with
threshold interaction second. No new model, window, target, or repair
is authorised by this audit.

## 2. Current architecture

Agent → DecisionRecord (24/session, portfolio_before/after,
submitted_orders, executions) → E5A attribution (119 rows, 106
EXECUTED labelled 100) → V1 (14f)/V2 (23f) builders → M-cells
(logistic/HGB) with permutation + missingness probes → foundation
track (PIT context → Chronos-2/TimesFM-3 → ForecastOutput → 11
derived features → diagnostic table) → conditional miner →
DiagnosticHypothesis → hypothesis_builder → FailureHypothesis →
ml_validation (review only). MemoryStore/gate/extraction untouched;
zero writes.

## 3. Complete ML data-flow (information discarded at each stage)

| stage | in → out | filter / threshold | discarded |
|---|---|---|---|
| trajectory join | 119 rows → 106 EXECUTED | participation filter | 6 NO_ORDERS + 6 unlabelled-edge rows + all sequential links |
| V1/V2 build | snapshots → 14/23 features | allowlists | order history, exposure path, context history (drawdown only survivor) |
| forecast context | 256 closes `<T` | univariate-first | cross-series/covariate structure (supported by models, unused) |
| derive | quantiles → 11 features | full-5d-paths-or-None | partial-path information (refused, correctly) |
| predictive cells | rows → Brier/AUROC | none | nothing (all rows scored) |
| miner universe | 16 cols → ~950 conditions | pairs need TRAIN presence | higher-order interactions (never enumerated) |
| miner select | universe → candidates | N≥15, Δ≥0.02, VALID confirm | 99.5% at N gate; VALID-flipped conditions |
| builder/validation | candidates → hypotheses | sample/effect/schema checks | (uncharged: zero arrivals) |

## 4. Model output analysis

* Counts: 106/106 AVAILABLE both models; 0 missing predictions.
* Chronos-2 q50-h5 range 2440–3524, width-h5 med 189 (132–347);
  TimesFM-3 width-h5 med 203 (143–450). Per-instrument medians
  separate cleanly (RELIANCE ~2527, TCS ~3300 — price levels, as
  expected for level forecasts).
* Variation across decisions/regimes: yes (tercile spreads below).
* Agreement: directional agreement 53/106; interval medians close
  (189 vs 203) but decision-level direction is uncorrelated.
* HGB (M3): VALID worse than B0 both targets; TEST better both
  targets — same small-sample family as M1/M2b, AUROC 0.66–0.74 on
  n≤36 (wide bands, no claim).

## 5. Representation information analysis (pre-mining)

TRAIN-tercile adverse rates (base in brackets). TRAIN shows spreads
on nearly every column (f_ret_1d 0.62/0.33 [0.50]; width 0.77/0.50;
drawdown-hi 0.83/0.36; nifty-hi 0.75/0.29); VALID and TEST frequently
reverse the direction (f_q10 VALID 0.31/0.58; instrument_return_5d
TEST 0.50/0.92 vs TRAIN 0.31/0.58). TEST base 0.74 compresses all
discrimination. `f_direction_consistency` is degenerate (constant).
**There is observable within-split information; it is not temporally
stable.** The miner therefore discards real-but-unstable spreads —
correct behaviour under its charter, and the reason "zero
hypotheses" ≠ "zero signal".

## 6. Miner rejection analysis

Chronos universe 953: N<15 → 948; Δ<0.02 → 3; no-VALID-confirm → 2;
candidates 0. TimesFM universe 949: 944 / 3 / 2 / 0. Near-misses:
`instrument=TCS:EQ` (TRAIN n=18 rate 0.556 Δ+0.056; VALID 0.389 vs
0.417 base — direction flip); `f_direction_consistency=low`
degenerate (n=36 rate=base). No candidate ever reached the builder or
validation layers — rejections are miner-internal (N/threshold/
consistency), never about missingness, calibration, or provenance.

## 7. Target analysis

100 labelled decisions: both-adverse 28, MAE-only 27, neither 45,
forward-only 0; agreement 73%. MAE⊃forward strictly: every 3-day
loser suffered excursion, but 27 excursion-sufferers recovered.
MAE range −13.1%…+1.6% (med −1.1%); MFE med +1.2%. adverse_MAE thus
flags transient pain including recovered positions — a defensible
risk proxy but a noisy "bad decision requiring repair" label. Any
future target work must pre-register whether it targets excursion,
terminal loss, or opportunity cost; that change is NOT authorised
here.

## 8. Context/memory analysis

The agent observes 3 of ~24 leaves; ML rows observe snapshots only.
Frozen trajectories already contain the missing sequential state:
per-session positions, exposure path, submitted_orders, 24-record
episodes, portfolio_before/after deltas. Absent from every ML
dataset: previous-action sequence, exposure trajectory, decision
history, context/version history, retrieved-knowledge history,
state transitions. A context/memory failure (e.g. repeated
accumulation without confirmation) is therefore structurally
invisible to the current representation. This is the largest
untested surface — F is plausible and unexamined, not confirmed.

## 9. Sequence analysis

Current: decision_t → features_t → prediction_t (independent rows;
only drawdown carries trajectory memory). Required for the repair
thesis: decision_(t-k:t) + context + portfolio + market →
failure-state_t. Frozen `baseline_result.json` trajectories are
sufficient to build sequence-level datasets without touching the
environment (24 ordered records/episode, portfolio snapshots,
order flow). Analysis only — no sequence features built.

## 10. Repairability analysis

| signal | evidence | mechanism | repairable? | required context | LearnedContext fit |
|---|---|---|---|---|---|
| wide forecast interval → elevated TRAIN adverse rate | 0.77 vs 0.50 (unstable cross-split) | accumulation under uncertainty | maybe | uncertainty regime + exposure trajectory | applicability_conditions expressible; corrective principle needs exposure state (absent) |
| negative forecast return → elevated TRAIN rate | 0.62–0.69 vs 0.33–0.50 (flips) | buying into forecasted downside | maybe | downside regime + recent actions | same gap as above |
| TCS:EQ elevated TRAIN rate | 0.556 vs 0.50 (VALID flips) | instrument-specific weakness | weak | instrument + regime (present) | expressible, but instability voids it |
| model disagreement | 53/106 agreement | uncertainty about regime | unknown | disagreement metric (derivable) | not yet represented |

No signal is currently both stable and repairable. Predictive signal
≠ repairable failure remains the binding distinction.

## 11. Failure points (ranked)

1. n=36 TRAIN with ~950-condition universe (C×G interaction).
2. Regime nonstationarity: prevalence 0.50→0.42→0.74; spread flips.
3. Point-in-time independence assumption vs sequential thesis (F).
4. Target asymmetry: MAE flags recovered positions (D).
5. Model disagreement 50% (E unresolved, not convicted).
6. Degenerate constants in schema (direction_consistency; rbi_stance).

## 12. What the NULL establishes

Scalar and conditional ML on independent decision rows cannot
demonstrate temporally held-out decision-quality information on
E5A-1/2/3 beyond prevalence; richer representations (V2, HGB,
Chronos-2, TimesFM-3) did not change that; the miner correctly
reports emptiness rather than manufacturing hypotheses.

## 13. What it does NOT establish

That no signal exists (within-split spreads exist); that foundation
models are useless (they were never given sequential/cross-series
inputs); that the target is wrong (only that it is noisy); that
repair is impossible (never attempted, correctly).

## 14. Recommended next experiment (ONE, pre-registered)

Sequence-aware diagnostic dataset (frozen trajectories only):
per-decision rows augmented with trailing-k action/exposure/context
summaries (k fixed upfront, e.g. 3 sessions) + miner rerun under
identical thresholds/targets/splits. If still empty, the honest
programme is a single pre-registered sample/regime expansion
contract — not more models. No agent/MemoryStore/gate changes; no
target change; no new windows beyond the contract.

## 15. Explicit stop conditions

Stop and re-audit if: sequence features still yield zero candidates
(→ expansion contract or thesis re-examination); any PIT/leakage
test fails; anyone proposes TEST-selected bands, new targets
mid-stream, or model shopping. No repair experiment until a
validated (accepted-for-review) hypothesis exists.

---
*Method: read-only analysis over frozen artefacts (`/tmp/m4_*.py`,
not committed); no code, evidence, or config modified; no new model,
window, target, or experiment run; no MemoryStore/agent contact.*
