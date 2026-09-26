# M4 Sequence-Feature Analysis — Verdict: M4-NULL (2026-09-26)

## 1. Headline results (Brier; B0 prevalence never beaten on VALID)

Primary adverse_mae — R0-log V .3165/T .3501; R1-log V .3451/T .4749;
R0-hgb V .3601/T .2242; R1-hgb V .3588/T .3956.
Secondary adverse_forward_3d — R0-log V .3032/T .1674; R1-log V .3093/
T .1784; R0-hgb V .2842/T .1796; R1-hgb V .2637/T .1639.

R0 reproduces M2b/M3 exactly. R1 never beats B0 on any VALID split;
on primary it is strictly worse than R0 for both models.

## 2. Against the 10 acceptance criteria

1. Beat B0: FAIL (all VALID cells worse than prevalence).
2. Beat R0: mixed — R1-hgb secondary improves on both splits
   (V .2637<.2842, T .1639<.1796); all other R1 cells worse.
3–4. VALID+TEST over B0: FAIL everywhere.
5. Calibration: FAIL — R1-hgb secondary log-loss V .7853 (B0 ~.58);
   R1-log primary log-loss V 2.33 / T 3.40 (confident miscalibration).
6. Permutation: behaves correctly (perm worse than model on both
   splits for R1-hgb secondary: V .3061, T .347) — necessary but
   moot without B0 improvement.
7. Missingness: PASS — probes equal B0 exactly; mild seq-support
   variation (R1-log primary miss T .2416 vs B0 .25) is not driving
   anything.
8. Leakage: PASS — both mutation tests green; integrity flags true.
9. Cross-instrument evidence: not established (no stable signal).
10. Interpretable condition: none produced.

## 3. Interpretation

The trajectory-derived sequential state available in frozen E5A
records (action counts, exposure/cash/equity/PnL changes and slopes,
prior rewards over k=3/5) carries no demonstrable out-of-sample
decision-quality information beyond prevalence under identical
models. The R1-hgb secondary TEST gain repeats the familiar
small-sample pattern (VALID fails, log-loss fails) and does not
survive the acceptance framework. Adding 24 history features to an
n=36 TRAIN problem steepens overfitting (R1-log primary TEST .4749).

## 4. Verdict

**M4-NULL. The sequence-feature branch stops here.** Per the stop
condition, no new features, models, windows, targets, or regimes
follow. No hypothesis was generated; nothing reached validation;
MemoryStore untouched; agent unchanged.

> The currently preserved trajectory representation does not provide
> demonstrable out-of-sample decision-quality information sufficient
> to construct a validated ML repair hypothesis.

## 5. What this does not close

The failure is now localised: snapshot (M1/M2/M3), forecast
(Chronos/TimesFM), and short-trajectory (M4) representations all
NULL under the same protocol. Remaining honest branches, each
requiring separate authorisation: a single pre-registered
sample/regime expansion contract, or target-formulation research.
Model shopping is exhausted as a response.
