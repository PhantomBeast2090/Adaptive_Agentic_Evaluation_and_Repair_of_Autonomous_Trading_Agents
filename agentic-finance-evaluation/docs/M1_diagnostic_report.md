# M1 Logistic-Regression Diagnostic Report — Verdict: M1-NULL

**Experiment:** `M1-logistic-20260926` under `data/frozen_traces/_m1/`
**Fingerprint:** `2a4d1b6b8e2ac0895400743b7abde285db7cd494a39bd76e94718efa005923e2`
(reproduced byte-identically on rerun)
**Code:** `evaluation/attribution/m1_experiment.py` (C=1.0, lbfgs, no tuning)
**Dataset (frozen, unmodified):** `data/frozen_traces/_ml/e5a_combined_v1.json`
**Permutation seed:** 20260926 (deterministic; alternate seed checked in tests)

## Dataset

| split | window | rows | positives (adverse_MAE) | prevalence |
|---|---|---|---|---|
| TRAIN | E5A-1 | 36 | 18 | 0.500 |
| VALID | E5A-2 | 36 | 15 | 0.417 |
| TEST | E5A-3 | 34 | 25 | 0.735 |

EXECUTED only; 0 rows dropped (MAE fully populated); high-VIX window
contributes 0 rows, retained in evidence as recorded. Missingness:
pre_trend_5d 40/106 (window-edge, structural), position/avg_cost 6/106
(pre-first-fill → encoded 0 + missing indicator), vix_tm1 8/106
(window-edge + 2023-06-29 data gap). Preprocessing (medians/means/stds,
TRAIN categories) fit on TRAIN only; unseen categories → zero vector.

## B0 (TRAIN prevalence = 0.50 everywhere)

- VALID: Brier 0.2500, log-loss 0.6931.
- TEST: Brier 0.2500, log-loss 0.6931.

## M1

- VALID: Brier **0.2964** (worse than B0 by +0.0464), log-loss 0.8264.
  Reliability: predictions cluster ~0.58–0.63 while observed rates span
  0.14–0.71 across bins — miscalibrated, near-flat discrimination.
- TEST: Brier **0.1827** (better than B0 by −0.0673), log-loss 0.5660.
  Reliability superficially closer — but see permutation result.

## Permutation (TRAIN labels shuffled, seed 20260926)

- VALID: Brier 0.2838 (also worse than B0, close to M1's 0.2964).
- TEST: Brier **0.2046** (also beats B0's 0.2500, close to M1's 0.1827).

TEST prevalence (0.735) differs sharply from TRAIN prevalence (0.50):
any model predicting above-0.5 probabilities — including a
permuted-label model — beats the constant-0.50 B0 there. The TEST
"improvement" is therefore a prevalence-shift artefact, not evidence of
learned decision-quality structure. The falsification check functioned
exactly as designed.

## Coefficients (association only, never causal)

Largest magnitudes: `pre_trend_1d__missing` +1.07 (window-edge artefact
indicator), `pre_trend_5d__missing` −0.44, `vix_tm1` −0.36,
`avg_cost` −0.33, `instrument=TCS:EQ` +0.33 / `RELIANCE:EQ` −0.33
(re-learned TRAIN instrument base rates), `pre_trend_1d` +0.26.
The model leans on a missingness indicator and TRAIN-window base rates —
unstable artefacts, not portable decision knowledge.

## Leakage audit

Feature payloads contain exactly the 14 frozen allowlist entries;
`forward_return_*`, `mae`, `mfe`, `hold_return`, `opportunity_return`
structurally excluded (constructor raises on overlap; tested). No future
VIX/prices/portfolio values; no oracle fields; no label-derived inputs.

## Interpretation

1. Useful out-of-sample decision-quality information beyond prevalence?
   **No.** Worse than B0 on VALID; TEST gain shared by the permuted null.
2. Stable interpretable candidate failure pattern? **No.** Dominant
   coefficients are missingness/instrument base-rate artefacts.

## Research decision

```text
M1-NULL
```

> M1 did not demonstrate evidence that the available decision-time
> contextual features provide reliable out-of-sample prediction of
> adverse decision quality under the tested temporal windows.

Per protocol: no feature additions, no target/window/threshold changes,
no further models, no TEST tuning, no repair hypothesis. The
environment's current decision-time representation (14 PIT features over
three same-regime BUY-only windows) appears insufficient for a
generalisable diagnostic — the open question is representation/regime
coverage, not model capacity.

## Reproducibility

9 M1 tests pass; full attribution suite 19 pass. Artefacts:
`config/preprocessing/splits/metrics_{b0,m1,permutation}/predictions/manifest.json`
under the experiment dir; code SHA + data SHA in manifest. Frozen E5A
evidence, agent, MemoryStore, validation/admission untouched. No model
object persisted (coefficients + preprocessing JSONs fully respecify it).
