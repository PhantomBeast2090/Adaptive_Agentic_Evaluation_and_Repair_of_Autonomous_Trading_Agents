# I2 Support-Construction Design (FAMILY FREEZE — frozen before execution)

## 1. Mandate

I2 is the LAST support-construction experiment. Family {K0, K1, K2, K3} is
complete and closed. K1 preferred; K2/K3 only if K1 fails and the
deterministic rule requires them. No new cells, rules, models, thresholds,
or split movements. No outcome labels before winner freeze. Single-pair
TEST triggers human consult, never automatic mining. Miner-NULL on the
winner is terminal (no I3).

## 2. Forensic basis (I2a, X/A-only)

I1: TRAIN 46 / VALID 19 / TEST 18 (gate 15/10/20). W1-T3 is a forced
unanimity region (66/66 non-contrast: VIX ∈ [18.35,28.12] ⇒ zero LOW dates;
holdings identical — C0 flat — across all cells ⇒ HIGH path cannot
discriminate). TEST's 18 contrasts are all W2-T3 (2022-01-25→03-11)
(HOLD,SELL) from divergent portfolio trajectories. Monotonicity proof: no
cell subset can exceed 18. Missing fuel: LOW-regime accumulation divergence
in TEST + more HIGH-straddling calendar.

## 3. Family

- K0: I1 six cells, frozen windows — calibration reference (must reproduce
  46/19/18) and never the winner.
- K1 (preferred): 18-cell full factorial from already-registered I1 values
  ({12,15,18}×{22,25,28}×{−0.05,−0.03}; new IDs C06..C17 lexicographic),
  identical windows/splits/dates. Mechanism: 12 new portfolio trajectories
  → new SELL/HOLD splits on existing HIGH dates.
- K2 (fallback): I1 six cells + pre-declared W2-T3 extension to 2022-06-30
  (62 sessions, VIX [17.69,25.64], full bars; VIX-only facts).
- K3 (fallback): 18 cells + extension.
Machine spec: `configs/choice_agent/i2_grid.yaml`.

## 4. Selection (I2c, Y-free, deterministic)

Eligibility = all support gates (15/10/20, regimes≥2, instruments≥3,
W2≥10, shared pair, rerun+anchor). Order [K1, K3, K2]; first eligible wins;
K2/K3 evaluated only if K1 fails. Rule uses contrast counts, regimes,
instruments, dates only. All candidates' tables published regardless.

## 5. Validity (summary; full argument in I2 design-gate report)

Selection is a function of (X, A(X)) with Y uncomputed until post-freeze —
non-circular by Kriegeskorte's independence criterion; outcome-blind
overlap restriction per Crump et al. 2009 (overlap-population estimand
disclosed); no hypothesis tested during selection so miner multiplicity
control (top-5, N≥15, permutation seed 20260926) is unchanged; Y-firewall
procedurally enforced (import test fails closed).

## 6. Stages

I2a forensics (done) → I2b support audit with frozen gates → I2c
deterministic selection → I2d winner freeze (`i2_grid.yaml` winner
annotation + `spec.json` + fingerprints in manifests; only then Y) →
I2e behavioural execution (post-auth) → I2f attribution → I2g frozen miner.
I2e–I2g require separate mining authorisation after the winner freeze.

## 7. STOP (terminal, no I3)

No candidate passes; outcome-dependent selection needed; frozen touch
needed; new values/rules/policy needed; firewall breach; single-pair TEST
(consult, no auto-mine); miner NULL on winner (I2-NULL terminal).

## 8. Pre-registration attestation

This document and `i2_grid.yaml` were written before any I2 cell executed
and before any outcome label was computed on any candidate. Spec
fingerprint is recorded into every run manifest.
