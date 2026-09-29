# I1 Behavioural Support Audit — I1-20260928

Spec fingerprint: `c7d66762c97e579a6c0b645f624ef3c93a65aadad04039a47246bef005973331`

## Per-branch behaviour

- W1-C0: sessions=189 classes={'BUY': 9, 'SELL': 7, 'MIXED': 3, 'HOLD': 170} quantities=[1.0, 2.0, 7.0, 10.0, 11.0] exposure=[0.0, 0.5481631569359855] exits=1 fp=`f97af641…`
- W1-C1: sessions=189 classes={'BUY': 0, 'SELL': 0, 'MIXED': 0, 'HOLD': 189} quantities=[] exposure=[0.0, 0.0] exits=0 fp=`d5442add…`
- W1-C2: sessions=189 classes={'BUY': 8, 'SELL': 17, 'MIXED': 5, 'HOLD': 159} quantities=[1.0, 2.0, 7.0, 11.0, 14.0] exposure=[0.0, 0.5516716173173106] exits=1 fp=`523336ee…`
- W1-C3: sessions=189 classes={'BUY': 9, 'SELL': 10, 'MIXED': 3, 'HOLD': 167} quantities=[1.0, 2.0, 10.0, 11.0] exposure=[0.0, 0.5481631569359855] exits=1 fp=`95394de4…`
- W1-C4: sessions=189 classes={'BUY': 9, 'SELL': 6, 'MIXED': 3, 'HOLD': 171} quantities=[1.0, 2.0, 9.0, 10.0, 11.0] exposure=[0.0, 0.5481631569359855] exits=1 fp=`017fbf78…`
- W1-C5: sessions=189 classes={'BUY': 11, 'SELL': 6, 'MIXED': 2, 'HOLD': 170} quantities=[1.0, 2.0, 4.0, 8.0, 9.0, 11.0] exposure=[0.0, 0.5206788997295916] exits=1 fp=`f7533c17…`
- W2-C0: sessions=187 classes={'BUY': 6, 'SELL': 8, 'MIXED': 0, 'HOLD': 173} quantities=[1.0, 2.0] exposure=[0.0, 0.6096361063446011] exits=1 fp=`3375728e…`
- W2-C1: sessions=187 classes={'BUY': 2, 'SELL': 2, 'MIXED': 0, 'HOLD': 183} quantities=[1.0, 2.0] exposure=[0.0, 0.2798245647229379] exits=1 fp=`fc28183f…`
- W2-C2: sessions=187 classes={'BUY': 17, 'SELL': 21, 'MIXED': 2, 'HOLD': 147} quantities=[1.0, 2.0, 7.0, 10.0, 11.0, 13.0] exposure=[0.0, 0.600696709751783] exits=1 fp=`e35eb025…`
- W2-C3: sessions=187 classes={'BUY': 6, 'SELL': 6, 'MIXED': 0, 'HOLD': 175} quantities=[1.0, 2.0] exposure=[0.0, 0.6096361063446011] exits=1 fp=`87100c6f…`
- W2-C4: sessions=187 classes={'BUY': 6, 'SELL': 9, 'MIXED': 0, 'HOLD': 172} quantities=[1.0, 2.0] exposure=[0.0, 0.6096361063446011] exits=1 fp=`3e7083c4…`
- W2-C5: sessions=187 classes={'BUY': 6, 'SELL': 8, 'MIXED': 0, 'HOLD': 173} quantities=[1.0, 2.0] exposure=[0.0, 0.6095157166530576] exits=1 fp=`717d2654…`

## Paired contrasts (cluster = window+date)

- TRAIN: clusters=127 contrasts=46 regimes={'MID': 12, 'LOW': 23, 'HIGH': 11} pairs={"('BUY', 'HOLD')": 18, "('HOLD', 'MIXED')": 2, "('BUY', 'HOLD', 'MIXED')": 3, "('HOLD', 'SELL')": 21, "('BUY', 'HOLD', 'SELL')": 1, "('HOLD', 'MIXED', 'SELL')": 1} w2=9
- VALID: clusters=122 contrasts=19 regimes={'MID': 19} pairs={"('HOLD', 'SELL')": 6, "('BUY', 'HOLD')": 11, "('HOLD', 'MIXED')": 2} w2=19
- TEST: clusters=127 contrasts=18 regimes={'MID': 7, 'HIGH': 11} pairs={"('HOLD', 'SELL')": 18} w2=18

Contrast instruments (6): ['ICICIBANK:EQ', 'INFY:EQ', 'RELIANCE:EQ', 'SBIN:EQ', 'TCS:EQ', 'YESBANK:EQ']
W2 total contrasts: 46

## Gate checks

- train>=15: PASS
- valid>=10: PASS
- test>=20: FAIL
- overlap_per_split: PASS
- regimes>=2: PASS
- instruments>=3: PASS
- w2>=10: PASS

## Verdict: I1-SUPPORT-FAIL

Branch closes permanently: no I2, no new grid, no relaxation. No mining, no repair, MemoryStore untouched.
## Reporting notes (post-audit, no gate impact)

- Note A (spec label error, descriptive only): the `role` strings for C1/C2
  in `i1_grid.yaml` are inverted. C1 (vix_low=12) NARROWS the LOW band
  (vix<12); C2 (vix_low=18) WIDENS it (vix<18). Evidence: W1-C1 is all-HOLD
  (189 sessions, zero orders) while W1-C2 is the most active W1 cell
  (8/17/5). Execution used the frozen numeric values throughout; only the
  English labels were wrong. The spec is left unedited post-freeze; this
  note is the correction.
- Note B (near-miss anatomy): TEST stops at 18 vs the pre-registered 20.
  W1-T3 (2020-07→09 rebound/MID grind) contributes 0 contrasts — the H0
  policy-convergence phenomenon persists where no boundary is crossed. All
  18 TEST contrasts are the single pair (HOLD,SELL) in MID/HIGH regimes.
  Against this: VALID passed 19 vs 10 (first non-degenerate VALID in
  program history; H0 had 0), TRAIN passed 46 vs 15 across 3 regimes and 6
  pairs, all 6 instruments carry contrasts, W2 contributes 46. The design
  moves support directionally (H0 TEST 0 → I1 TEST 18) but does not reach
  the bar for defensible miner confirmation. The 20 is NOT relaxed.
- Note C (integrity): C0-W1 full re-execution bit-identical PASS;
  C0-W1 behavioural payload == frozen G1-A-20260926 payload PASS
  (189 records, metrics, budget all byte-identical); anchor redefinition
  (fingerprint covers evaluation_id) documented pre-audit in
  `i1_grid.yaml`/`I1_IDENTIFIABILITY_DESIGN.md`; `git status` shows zero
  tracked modifications (only additive I1/H0 files untracked; raw-data
  gitlink pointers pre-date I1); conditional miner never invoked;
  LearnedContext/MemoryStore never imported; no repair attempted.

## Verdict (restated): I1-SUPPORT-FAIL (I1-NULL)

Per pre-registered STOP conditions the branch closes permanently: no I2,
no third grid, no threshold relaxation, no further deterministic-policy
variants on this evidence.
