# I1 Identifiability Design (DESIGN GATE — frozen before execution)

## 1. Objective

I1 is an **identifiability experiment**, not strategy optimisation, threshold
tuning, or model benchmarking. Success = legitimate, pre-registered,
reproducible behavioural overlap sufficient to test whether a failure
mechanism can be identified and later repaired. Finding a profitable cell is
explicitly NOT success.

## 2. Forensic basis

F2R/F3/G1/H0 form a chain of Class-B (support) NULLs with one shared
structure: a deterministic regime-gated policy on a single market path
produces actions perfectly confounded with regime episodes (deterministic
positivity violation). H0 proved capital variation creates genuine
same-regime disagreement (19/26 LOW-regime) but only at transition episodes
in TRAIN. I1 moves the variation to the decision boundary itself: varying
VIX_LOW/VIX_HIGH/TREND_MIN moves regime boundaries, so the same market date
falls in different regimes under different cells — manufacturing paired
action disagreement in every split, not just TRAIN transitions.

## 3. Grid (one-factor-at-a-time, outcome-blind)

C0 (15.0/25.0/-0.05) = frozen G1 reproduction anchor. C1/C2 bracket VIX_LOW
(12/18). C3/C4 bracket VIX_HIGH (22/28). C5 reuses the F0-frozen TREND_MIN
(-0.03). Rationale is arithmetic symmetry around frozen values; no outcome
was viewed (no I1 cell has executed as of this writing). Six cells only —
no additions, no deletions, no post-hoc movement. Framing: **controlled
policy-boundary perturbation for behavioural identifiability** — never "six
agents", never "natural variation".

## 4. Windows

W1 = 2020-01-01→2020-09-30 (G1-A-equivalent, comparability). W2 =
2021-07-01→2022-03-31, selected by the pre-declared VIX-only rule: first
quarter-aligned 9-month window starting ≥2021-04-01 with min VIX ≤15 and
max VIX ≥28. Outcome: W2 has VIX n=187, min 11.71, max 31.98 (scan touched
VIX closes only; no returns/actions/outcomes). Feasibility (not selection):
all 6 names have 187 complete EQ bars in W2 vs 188 in W1.

## 5. Splits, clusters, taxonomy

Within-window chronological thirds pooled across windows (TRAIN = W1_T1 ∪
W2_T1, etc.; exact boundaries in `configs/choice_agent/i1_grid.yaml`).
Cluster = (window, market date); branches never counted as independent
market samples (H0 precedent). Action classes BUY/SELL/MIXED/HOLD from
submitted order sides; paired contrast = ≥2 cells disagreeing in class on
the same cluster. Regime labels use frozen C0 bands (fixed date attribute).
Full machine spec: `configs/choice_agent/i1_grid.yaml` (cells, windows,
splits, gates, miner freeze, falsification, STOP, taxonomies).

## 6. Support gate (mining locked behind ALL of it)

6/6 cells executed; bit-identical reruns; W1-C0 behavioural payload
(decision_records + metrics + budget_usage, canonical JSON) equals frozen
G1-A-20260926 payload (reproduction anchor; corrected 20260928 pre-audit —
full-artefact `fingerprint()` covers `evaluation_id` by design, so raw
fingerprint equality across experiment IDs is impossible); TRAIN ≥15 / VALID ≥10 / TEST ≥20
paired-contrast clusters; action overlap (no BUY/HOLD/SELL segregation) in
every split; contrasts in ≥2 C0 VIX regimes; contrasts on ≥3 instruments;
W2 contributes ≥10 contrasts. Verdict vocabulary: I1-SUPPORT-PASS,
I1-SUPPORT-FAIL (I1-NULL), I1-INFRA-FAIL. On PASS: STOP and request mining
authorisation. On FAIL: branch closes permanently — no I2, no new grid, no
relaxation.

## 7. Identifiability rule

Policy disagreement ≠ failure-mechanism evidence. I1 creates conditions
under which a mechanism could be identified; outcome analysis comes later
under the frozen miner (N≥15/Δ≥0.02/top-5/seed 20260926) plus
cross-window-transfer falsification.

## 8. Implementation plan (on approval — now authorised)

`configs/choice_agent/i1_grid.yaml` (this spec), `scripts/run_i1.py`
(config loop + `_i1/` fingerprinted persistence + `--audit` support
accounting), `tests/agents/test_i1_branches.py` (Tier-1: spec freeze,
determinism, isolation, contract validity, provenance shape), support audit
→ `docs/I1_BEHAVIOURAL_SUPPORT_AUDIT.md`. No attribution/mining/repair/
MemoryStore in I1. No frozen touches (additive only).

## 9. Pre-registration attestation

This document and `i1_grid.yaml` were written before any I1 cell executed.
Spec fingerprint is recorded into every run manifest; any post-freeze edit
to either file invalidates the pre-registration and must be declared as a
protocol breach, not a silent fix.
