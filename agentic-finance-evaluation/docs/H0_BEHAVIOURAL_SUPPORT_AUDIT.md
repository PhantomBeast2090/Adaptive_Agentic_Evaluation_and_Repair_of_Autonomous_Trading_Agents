# H0 Behavioural Support Audit — Verdict: H0-SUPPORT-FAIL

## 1-5. Objective, constraints, grid, window, intervention

Capital-only variation (S0 100k / S1 25k / S2 50k / S3 200k), frozen
MultiAssetChoice, identical 2020-01-01→2020-09-30 market path.
4 branches × 189 sessions, all deterministic.

## 6. Branch fingerprints

S0 425f5ddb / S1 a69a379f / S2 f0610249 / S3 48648161 (distinct —
capital changes trajectories, as designed).

## 7. Deterministic integrity

Same state+data reruns bit-identical (tests); market legs
portfolio-independent by construction; branch isolation asserted
(no shared portfolio objects); mutation tests green.

## 8-9. Action/quantity distributions

Per branch BUY+SELL+HOLD all present; quantities {1.0, 2.0,
partials, flattens}; all 6 instruments traded; no-short holds;
BINDING honest; costs reconcile.

## 10. Contextual overlap (the core result)

26/189 paired dates disagree (13.8%), ALL in TRAIN thirds:
LOW-regime 19/26 dates disagree (73%) — genuine same-regime,
state-conditioned variation (e.g. S3 BUY×2 while S1 HOLDs).
MID 3/74, HIGH 4/89. VALID: 59 paired, 0 disagree. TEST: 66
paired, 0 disagree.

## 11. Date-cluster support

Clusters preserved (date = unit); branches never counted as
independent market samples.

## 12. Split support

TRAIN 64 paired / 26 contrasts ✓; VALID 59 / 0 ✗; TEST 66 / 0 ✗.
Gate requires VALID≥10 + TEST≥20 contrast support: FAILED.

## 13. Independence treatment

Paired/cluster-aware throughout; no pseudo-replication.

## 14. Edge cases

MID-grind months: all branches identical HOLD (policy converges —
itself a behavioural finding, not support). Crash HIGH: branches
differ only in SELL size/timing (4 dates).

## 15. Verdict: H0-SUPPORT-FAIL

Not infra (integrity all green). Capital variation creates
overlapping support ONLY at regime-transition episodes (TRAIN);
VALID/TEST regimes produce no state-conditioned variation.
Classification: threshold/sample interaction is secondary; primary
cause is policy convergence outside transitions (agent-behaviour
class). No mining, no repair, no new states.

## 16. Next gate

Support-gated diagnosis remains unauthorised. Honest options for a
future milestone: (a) transition-centred windows (transition-only
splits — risks outcome-adjacent date-picking, needs authorisation);
(b) close the capital-state branch per protocol. Recommended: (b)
unless (a) is explicitly authorised with pre-registered dates.
