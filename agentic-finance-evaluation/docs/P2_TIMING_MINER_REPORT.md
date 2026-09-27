# P2 Entry-Timing Miner — Report and Verdict: formulation-level NULL

## 1. Locked definition (executed as specified)

Per EXECUTED BUY at session t: `timing_regret =
(C_{t+3}−C_{t+1})/C_{t+1} − (C_{t+3}−exec)/exec` — hypothetical
next-session entry timing benchmark. Execution prices from frozen
`attribution.json` legs; C_{t+1}/C_{t+3} from the frozen engine's
exact-bar lookup over each artefact's frozen grid (engine
instantiated read-only, unmodified). Language discipline kept:
benchmark only, never "the trade to make"; one-step hypothetical
fill acknowledged.

## 2. Protocol choices (fixed pre-run)

Timing-adverse = regret > +0.01 (frozen ADVERSE_BAND reuse, strict).
Missing C_{t+1}/C_{t+3} → None (8 such rows, all in E5A-2 holiday
edges; never interpolated). SELL → None (zero SELL rows exist).
Cost note: legs are gross; no cost model introduced.

## 3. Target distribution (non-degenerate — experiment proceeded)

98 labelled of 106; adverse 16/98. Splits: TRAIN 36 @ 0.139 (5 adv),
VALID 28 @ 0.107 (3 adv), TEST 34 @ 0.235 (8 adv). Range −0.039…
+0.074, median ~0.0.

## 4. Miner result: 0 candidates (universe 5911, status COMPLETE)

TRAIN supports only 5 positives: any N≥15 condition caps at rate
5/15 = 0.33 vs base 0.139 — arduous but not impossible; none cleared
TRAIN Δ≥0.02 *and* VALID confirmation. Rejections are miner-internal
(support/delta/confirmation), never missingness/provenance.

## 5. Falsification (decisive)

Label permutation (seed 20260926): **5 candidates** vs 0 on real
labels (top TRAIN Δ 0.038). Shuffled-timing: 0. At 10–14% base rates
with n≤36, chance VALID confirmations occur — real labels performing
*worse than chance* is strong evidence against a stable timing
mechanism, and simultaneously a caution that the miner's confirmation
bar is lenient at low prevalence. Integrity flags true; missingness
probes equal baseline.

## 6. Hypotheses, validation, repair

Zero candidates → zero hypotheses → validation never reached →
nothing toward LearnedContext. Repair-vocabulary question (§13 of
protocol) is moot: no condition exists to translate. Suppression-vs-
quality discipline preserved (nothing suppressed, nothing claimed).

## 7. Verdict: CASE B — formulation-level NULL

P2 counterfactual diagnosis produced no validated repairable
mechanism under the frozen agent and E5A evidence. The timing branch
stops here: no more features, models, windows, or targets follow
from it. Artefacts: `data/frozen_traces/_ml_sequence/
TIMING-20260926/` (fp `394548a4…`), code `evaluation/attribution/
timing.py`, `scripts/run_timing.py`, `tests/ml/test_timing.py`.
MemoryStore untouched; agent unchanged; frozen engine/environment/
contracts intact.
