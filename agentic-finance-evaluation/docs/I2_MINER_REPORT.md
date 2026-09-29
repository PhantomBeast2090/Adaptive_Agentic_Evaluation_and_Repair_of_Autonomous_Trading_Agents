# I2 Miner Report — Verdict: I2-NULL (terminal, no I3)

## 1. Provenance

Frozen K1 winner (18 cells × W1/W2; selection.json `I2-20260928`).
Attribution: frozen DecisionAttributionEngine via run_f1's
CachedAttributionEngine shim (byte-identical semantics), 36 branches,
~8.6k rows → `data/frozen_traces/I2-W*-C*`. Features: V1+V2+sequence R1
merge (run_f2 pattern): 2458 labelled EXECUTED rows. Splits (I2 thirds):
TRAIN/VALID/TEST labelled — MAE 1743/333/382 @ 0.685/0.739/0.605;
forward 1728/333/382 @ 0.406/0.333/0.432. Miner: frozen
conditional_miner (N≥15/Δ≥0.02/top-5), permutation seed 20260926,
hypothesis building + validation-review, cross-window transfer check.
Artefacts: `data/frozen_traces/_ml_i2/I2-20260928/results.json`.

Performance shim (disclosed): the frozen miner re-derives each row's
~1500 condition tuples once per universe condition (~7423×); at I2 scale
(~7h per mine call by timing probe) execution was infeasible. A
memoization shim in `scripts/run_i2_diagnosis.py` (F1 CachedAttributionEngine
precedent) eliminates redundant recomputation with bit-identical outputs;
equivalence proven by `tests/agents/test_i2_diagnosis.py::test_shim_equivalence`
(identical universe, conditions, split stats). Frozen miner file untouched;
thresholds and logic unchanged.

## 2. Results

Universe 7423 both targets. MAE: 5 candidates (top TRAIN Δ 0.315);
permutation 5 (top Δ 0.215). Forward: 5 candidates (top Δ 0.594);
permutation 5 (top Δ 0.219). **Permutation parity on count (5v5) both
targets** — identical to F2/F2R, now under adequate support.

Closest observations (recorded as unevaluated candidates, NOT mechanisms):
- MAE H1 `[holdings_value=low, instrument=YESBANK:EQ]` (F-CONC): TRAIN
  60@1.000, VALID 9@1.000 (+0.261), TEST 28@0.786 (+0.181), transfer pass
  both windows. Blocked by: permutation count parity (experiment-level)
  and single-instrument confinement (YESBANK-only; frozen criterion 5).
- Forward H5 `[holdings_value=low, seq_cash_min_k3=low]` (F-CONC/F-CASH):
  TRAIN 22@0.909, VALID 51@0.824 (+0.490), TEST 6@0.667 (+0.235),
  transfer pass, no instrument clause. Blocked by: permutation count
  parity (experiment-level).
- All other candidates fail TEST confirmation (rates below baseline,
  n≤3) or transfer. Forward H1 transfer matched_n=0 both windows (no
  transferable support). MAE H2/H3 collapse on TEST (0.333 vs 0.605).
- Validation-review ACCEPT_FOR_ADMISSION_REVIEW (H2/H3/H5 MAE; H2/H3/H4
  forward) is schema/support acceptance only — per F2R precedent, not
  held-out confirmation.

## 3. Falsification battery (spec §falsification)

1. real>perm count AND delta: FAIL (5v5 both targets; delta passes).
2. VALID confirmation: H1/H5 pass; others fail.
3. TEST confirmation: H1 (n=28, +0.181) and H5 (n=6, +0.235) pass
   numerically; all others fail.
4/6. Cross-instrument / no single-instrument survivor: H1 FAILS
   (YESBANK-only). H5 passes nominally (no instrument clause).
5. Cross-window transfer: H1, H5 pass; H2/H3-MAE, H1-forward fail.
7. Vacuous VALID: none of the TEST-confirming candidates vacuous
   (VALID n=9/51).
8. Missingness: no separate probe (binary targets; F2R precedent N/A).
9. Determinism: miner path seed-fixed; behavioural rerun + anchor PASS.
10. Suppression-vs-quality: moot (no repair reached).

## 4. Verdict: I2-NULL (terminal)

No candidate survives the pre-registered battery: experiment-level
permutation parity binds both targets, and the strongest MAE survivor is
single-instrument-confined. These are the exact failure modes the frozen
rules were written to catch (F2R §§6/8). Overriding them because H1/H5
"look good" would be the outcome-tuning loop (§14) the program forbids.

Classification upgrade: this is the program's first **Class-C scientific
null** — adequate behavioural support (56/32/22 contrasts; 1743 TRAIN
labels), frozen diagnostic protocol executed as specified, no validated
mechanism. Prior NULLs were Class B (support failure); this one is not.

Scope discipline: the NULL states "no failure mechanism validated under
the frozen diagnostic protocol (conditional miner, R1 schema, MAE/forward
targets, overlap population of HIGH/transition episodes)". It does not
state "no mechanisms exist", nor does it indict ML-in-general: one miner
family, one schema, two targets. The throttle-only repair vocabulary,
MemoryStore admission path, and the repair→verification half of the loop
remain untested by design, not by accident.

Terminal: no I3, no variant hunt, no threshold relaxation. No
MemoryStore writes. No repair attempted.
