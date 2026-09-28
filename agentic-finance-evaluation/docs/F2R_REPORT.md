# F2R Report — Verdict: F2R-NULL (protocol adjudication)

## 1. Repository state

HEAD `9d656c9` at run; tree clean except pre-existing raw-data
gitlinks. Split spec `aba2ade5…` verified stable before mining.

## 2. F2R split (as approved)

TRAIN = F1R-B (53) + F1R-A < 2020-02-15 (66) = 119 rows.
VALID = F1R-A 2020-02-15..2020-03-10 = 6 rows (accepted weak).
TEST = F1R-A > 2020-03-10 = 30 rows (SELL-only transition).

## 3. Label support

MAE: TRAIN 119 @0.571 (68 adv; BUY 114/SELL 5), VALID 6 @0.667,
TEST 30 @0.800. Forward: TRAIN 119 @0.218, VALID 6 @0.667, TEST 30
@0.500. Instruments balanced in TRAIN (41/39/39) and TEST (10/10/10).

## 4. F2 results

Universe 7149 both targets; 5 candidates each (all pair-conjunctions;
BUY-leaning TRAIN conditions).

## 5. Falsification

Label permutation (seed 20260926): 5 candidates per target with
comparable top TRAIN deltas (0.218/0.248) — parity with real labels.
Shuffled-regret N/A (binary targets; protocol's applicable null is
the permutation, executed).

## 6. Hypotheses: 0 validated

Forward: every VALID confirmation is rate 1.0 on n=1 (vacuous);
TEST rates None/0.0. MAE: TRAIN 0.80–0.87 (n=15) and VALID 0.80–1.0
(n=2–5) collapse on TEST (0.58–0.80 vs 0.80 baseline) — TEST
confirmation fails on all five. All MAE survivors confine to
`instrument=RELIANCE:EQ` (single-instrument artefact flag).
Validation-review ACCEPTs on schema/support grounds are recorded but
are not held-out confirmations. No DiagnosticHypothesis qualifies;
none built beyond miner rows (0 persisted hypotheses).

## 7. Repair status

LearnedContext: untouched. MemoryStore: untouched. Agent: unchanged.
F3: not executed. F4: not executed.

## 8. Scientific verdict: F2R-NULL

Classification: (1) TEST-confirmation failure is binding — compounded
by the accepted VALID weakness (n=6 → n=1–5 confirmations cannot bear
weight; per protocol this is NOT evidence of mechanism absence);
(2) permutation parity → threshold/sample interaction dominates;
(3) single-instrument confinement; (4) BUY→SELL regime segregation
means TRAIN conditions cannot transfer to TEST by construction.
The SELL-side behaviour exists (36 crash rows) but yields no
reproducible failure mechanism under the frozen protocol.

## 9. Recommendation

Close the diagnosis branch as specified: no more miners/models/
windows/targets on this evidence. The honest remaining questions
(each needing fresh authorisation) are the named VIX-transition
expansion contract or the agent-choice redesign proposal — not
another mining variant. The throttle-only repair vocabulary was
never reached and remains untested by design, not by accident.
