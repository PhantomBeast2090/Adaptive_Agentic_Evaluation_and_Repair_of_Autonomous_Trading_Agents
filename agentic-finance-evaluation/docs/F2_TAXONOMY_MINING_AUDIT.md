# F2 Taxonomy-Mining Audit — Verdict: F2-NULL, NO REPAIR

## Design (pre-registered before mining)

Splits (date/regime-defined): TRAIN = F1R-B + F1R-A<2020-03-01;
VALID = F1R-A 2020-03-01..2020-04-30 (crash); TEST = F1R-A>2020-04-30
(recovery). Targets adverse_mae/adverse_forward_3d (frozen bands).
Miner: frozen conditional_miner over R1 schema (45 num + 4 cat),
thresholds N>=15/Δ>=0.02/VALID-confirm/top-5 unchanged.
Falsification: label permutation (seed 20260926).

## Results

MAE: TRAIN 119 @0.571, VALID 36 @0.778, TEST 0 labelled.
Fwd: TRAIN 119 @0.218, VALID 36 @0.528, TEST 0 labelled.
Universe 7149 both targets; 5 candidates each; permutation 5 each.

## Why no candidate validates

1. **TEST structurally empty.** Recovery-window decisions lack
   t+1..t+3 legs inside the frozen F0R-A window (edge missingness).
   TEST confirmation is impossible — a split-design defect, reported
   not repaired (any re-split now would be post-hoc). Lesson:
   splits must be checked for labelled support before mining.
2. **Permutation parity.** Shuffled TRAIN labels yield 5 candidates
   per target — chance-level output. Real labels do no better.
3. **Single-instrument confinement.** All MAE candidates condition
   on `instrument=RELIANCE:EQ`; criterion 5 (beyond one
   instrument/window cell) fails.
4. **Vacuous VALID confirmations.** All fwd candidates confirm at
   rate 1.0 on n=1; MAE VALID rates (0.80-0.83) barely exceed the
   crash-window base (0.778).
5. Validation review accepted 4-5 candidates on schema/support
   grounds, but acceptance ≠ held-out confirmation; without TEST,
   F3 admission is correctly unreachable.

## Taxonomy mapping (informational only)

Candidates touch F-ACC (exposure slope/change), F-CONC
(instrument/returns/holdings), F-CASH (cash change); F-VOL absent
(by construction: MID regime never initiates). Mapping is moot —
no mechanism validated.

## Verdict

**F2-NULL. No LearnedContext, no MemoryStore write, no repair run.**
The chain stops at validation: hypotheses exist as unevaluated
candidates only. Artefacts: `data/frozen_traces/_ml_f1/F2-20260926/`
(fp `7dbb5186…`), `scripts/run_f2.py`. Code: miner column params
(used), `F1_SUBDIR` persistence param. Frozen engine/env/contracts
untouched (CachedAttributionEngine shim proven 18/18 leg-identical;
lives in the runner, not frozen code).
