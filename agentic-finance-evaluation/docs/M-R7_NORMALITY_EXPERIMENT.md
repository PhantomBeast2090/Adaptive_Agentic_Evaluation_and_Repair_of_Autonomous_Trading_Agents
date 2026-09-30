# M-R7 — Mechanism-Relative Normality Sensitivity Experiment

## Research question

How should an adaptive external-repair environment define protected
normal behaviour when a diagnosed behavioural failure mechanism is
distributed across market regimes? M-R7 compares three pre-registered
normality definitions over an identical candidate set. The primary
object is the normality definition, not a repair.

## Design (frozen before adjudication)

- N0 regime-protected (control): calm VIX sessions protected — reproduces M-R6.
- N1 mechanism-relative: protected exactly when the exposure mechanism is absent.
- N2 hybrid: protected only when calm AND mechanism absent.
- Same dataset, agent, policy, windows, adapter, detectors, mechanism,
  candidates, IDs, params, compile rules, serving path, gates.
- Normality functions accept (record, mechanism) only (signature-tested).

## Conflict analysis (descriptive, pre-adjudication)

| Spec | Protection coverage | Mechanism coverage | Conflict rate |
|------|--------------------:|-------------------:|--------------:|
| N0 | 0.374 | 0.374 | 0.870 |
| N1 | 0.626 | 0.374 | 0.000 |
| N2 | 0.049 | 0.374 | 0.000 |

N0's conflict rate (0.87) quantifies the M-R6 bind: 87% of protected
sessions exhibit the diagnosed mechanism. N1/N2 eliminate conflict by
construction; N2 protects only 6 of 123 sessions.

## Adjudication (per spec, independent)

| Spec | Selected | Rejected | Verdict |
|------|----------|----------|---------|
| N0 | none | 9/9 | NULL (reproduces M-R6 exactly: same IDs, reasons) |
| N1 | none | 9/9 | NULL |
| N2 | none | 9/9 | NULL |

N1/N2 rejections are informative, not vacuous: exposure_cap and
quantity_reduction candidates under N1/N2 fail normal-preservation
because their effects leak onto mechanism-absent sessions (e.g. breadth
caps binding during 1–2-name accumulation); max_quantity candidates
fail on bootstrap power (upper == 0.0). The binding constraint thus
shifts from conflict-rate (N0) to intervention-specificity (N1/N2) —
the sensitivity result.

## Downstream

No spec admitted any repair: held-out NOT_CONSTRUCTED, no MemoryStore
writes, persistence/rollback NOT_ATTEMPTED, replication NOT_ATTEMPTED.

## Negative controls

Opposite-side block refused at eligibility; unscoped hold_all
UNCOMPILABLE; total suppression rejected by the inactivity guard
(see controls.json). Rejected candidates never entered MemoryStore.

## Interpretation

Per the pre-registered language: M-R7 demonstrates that the observed
natural-market NULL is robust across the pre-registered normality
definitions tested. It does not claim impossibility. The M-R6 NULL was
conditional on its regime-protected definition, but changing the
operational specification did not change repair admissibility here —
the evidence locates the remaining barrier in intervention
specificity (repairs whose effects spill beyond the diagnosed
condition) rather than in normality conflict alone.

## Limitations

Single mechanism (exposure), single diagnostic window, single agent;
bootstrap CIs assume approximate stationarity; calm-regime-only
mechanisms untested; no weight-level claims.
