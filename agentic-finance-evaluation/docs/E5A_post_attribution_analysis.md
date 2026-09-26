# E5A Post-Attribution Conditioning Analysis (Window 1)

**Experiment:** `E5A-deterministic-attribution-20260926`
**Artefact:** `data/frozen_traces/E5A-deterministic-attribution-20260926/`
**Attribution fingerprint:** `14ce55e5ce8722b86318d2aacb9c288a8d912346a70958c60430dd72a9e93616`
**Status:** infrastructure accepted as operational; deterministic-baseline verdict NULL.
**Scope:** BUY decisions only (0 SELL observed). No ML trained. No repair proposed.

This document is a persisted record of the analysis reported for review.
The frozen E5A artefact it analyses is unaltered. Machine-readable
companion: `data/frozen_traces/E5A-deterministic-attribution-20260926/conditioning.json`
(schema documented in §19; produced by the same read-only analysis).

---

## 1. Dataset summary

- 42 rows: 36 EXECUTED (all BUY; RELIANCE:EQ × 18, TCS:EQ × 18) + 6 NO_ORDERS.
- 24 NSE sessions, 2023-05-15 → 2023-06-15. All 36 executed rows DECIDABLE.
- Leg coverage: forward_1d/forward_3d/MAE/MFE/hold_return/opportunity_return
  36/36; pre_trend_1d 32/36, pre_trend_3d 28/36, pre_trend_5d 24/36
  (window-edge missingness only, expected).

## 2. Participation analysis

- 18/24 sessions acted; 6/24 NO_ORDERS clustering 2023-06-08 → 2023-06-15
  with `cash_before = 0`, `exposure_before = 1.0`, nonzero hold-drift rewards.
- Mechanism: cash exhaustion — the benchmark buys 2 shares/session until
  cash reaches zero on 2023-06-07. Environment-driven non-participation,
  preserved with `opportunity_return = None` (no counterfactual invented).

## 3. Adverse outcome base rates

- `adverse_forward_3d` (forward_return_3d < −0.01): **9/36 = 0.250**.
- `adverse_MAE` (MAE < −0.01): **18/36 = 0.500**.
- Thresholds are the frozen E5A definitions (±1% directional band
  convention); no alternative thresholds introduced.

## 4. Pre-trend conditioning (PIT-pure, ≤ t−1 legs)

Bands ±0.01 (transparent, not fitted):

| band | 1d: N / fwd / MAE | 3d: N / fwd / MAE | 5d: N / fwd / MAE |
|---|---|---|---|
| negative | 4 / 0.00 / 0.25 | 8 / 0.12 / 0.25 | 5 / 0.00 / 0.60 |
| flat | 24 / 0.21 / 0.42 | 14 / 0.21 / 0.64 | 10 / 0.30 / 0.50 |
| positive | 4 / 0.25 / 0.75 | 6 / 0.33 / 0.50 | 9 / 0.33 / 0.56 |

Continuous `pre_trend_3d`: adverse rows −0.0118…+0.0329; non-adverse
−0.0276…+0.0328 — full overlap. **The hypothesised "persistent negative
trend + BUY → adverse" pattern is NOT present**; negative-trend rows
adverse less often (tiny N; direction reported, nothing claimed).

## 5. VIX conditioning

t−1 VIX range 11.12–13.29 (always LOW regime; 25.0 never approached, so no
threshold rule is testable). Terciles (N≈11): fwd-adverse low 0.18 / mid
0.36 / high 0.08 — no coherent signal.

## 6. Portfolio conditioning

Exposure rises monotonically 0 → 0.98 (pure accumulation), so exposure
terciles ≡ temporal thirds (mid-window worst: fwd 0.33 / MAE 0.67) —
one confounded finding, not two. Cash is the inverse proxy. avg_cost and
realised/unrealised PnL are available via persisted
`baseline_result.json` position snapshots (not the flat CSV).

## 7. Action conditioning

BUY-only. All findings concern BUY decisions and do not generalise to SELL.

## 8. Instrument conditioning

RELIANCE fwd 0.222 / MAE 0.444 vs TCS 0.278 / 0.556 (N=18 each —
descriptive only, not conclusive).

## 9. Temporal conditioning

Early 0.25 / mid 0.33 / late 0.17 (fwd); MAE 0.42 / 0.67 / 0.42.
Diagnostic only; no causal claim. Early-window rows with missing
pre-trend legs show elevated adverse rates (N=4–12) — window-edge
artefact, not a rule basis.

## 10. Candidate deterministic rules

**None.** No band, threshold, VIX level, exposure level, or instrument
split satisfies the validity criteria (PIT-visible, observed, unfitted,
interpretable, held-out-testable). Deterministic-baseline verdict: NULL.

## 11. Sample-size assessment

N=36 supports base rates + exploration only. Single contiguous LOW-VIX
BUY-only regime cannot support temporal TRAIN/VALID/TEST splits or
generalisation claims.

## 12. Required additional E5A windows

Two pre-specified calendar windows (2023-06-16→07-15, 2023-07-17→08-15,
NSE-grid snapped, outcome-blind) plus one objectively selected high-VIX
window (market-only selection rule, defined before inspecting outcomes).

## 13. ML feature contract (proposed, not built)

Row = one EXECUTED decision. Decision-time inputs: pre_trend_1d/3d/5d,
VIX t−1, cash, position, exposure, avg_cost, realised/unrealised PnL,
portfolio value, instrument, action, quantity. Never as inputs:
forward_return, MAE, MFE, hold_return, opportunity_return.

## 14. ML target definition

Primary: `adverse_MAE`; secondary: `adverse_forward_3d`. Justification:
excursion captures decision-quality risk the buy-and-hold path masks.

## 15. ML temporal split design

Across windows (earlier → TRAIN, later → VALID, future held-out → TEST).
Never shuffled; never trained/tested on the same 36 decisions.

## 16. Baseline models

B0 prevalence (0.250 / 0.500) → B1 deterministic (currently NULL; ML must
beat prevalence alone) → M1 logistic regression → M2 tree-based only if
multi-window N allows. No model zoo.

## 17. Calibration metrics

Calibration, Brier score, log-loss, reliability; ranking diagnostics only
if N allows. Accuracy never central.

## 18. Null/permutation test design

Timestamp/label permutation must destroy signal; if shuffled performance
matches real performance, the signal is not credible.

## 19. Conditions for "ML informative"

Better-than-prevalence calibration + temporal held-out generalisation +
permutation null passed. Otherwise report null and stop. No MemoryStore
write without validation/admission in any case.
