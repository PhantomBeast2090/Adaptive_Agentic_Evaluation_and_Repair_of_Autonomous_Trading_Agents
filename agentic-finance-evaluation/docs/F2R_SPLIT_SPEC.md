# F2R Pre-registered Temporal Split (frozen 2026-09-26)

Repair of the F2 support defect: original TEST (recovery window) was
structurally empty of labelled rows. This split is selected from
calendar/support constraints only — never from candidate outcomes.

## Boundaries (ISO dates, chronological, non-overlapping)

* TRAIN: F1R-B (all 53 labelled rows) + F1R-A with
  decision_timestamp < 2020-02-15. Expected 119 rows.
* VALID: F1R-A with 2020-02-15 <= ts <= 2020-03-10. Expected 6 rows.
* TEST: F1R-A with ts > 2020-03-10. Expected 30 rows.
  Latest supported attribution date: 2020-03-24 (3-session forward
  buffer required; later sessions lack t+1..t+3 legs).

## Accepted limitations (deliberate, not adequate power)

* VALID n=6: confirmation on six rows is weak by construction.
  Survival there is necessary but never sufficient evidence.
* Action/regime transition: TRAIN is BUY-dominant (114/119);
  VALID/TEST are SELL-only. This is NOT IID validation; transfer
  across the transition is separately reported, never assumed.
* Full protocol still required: TRAIN discovery + VALID + TEST +
  permutation survival + support + interpretability.

## Frozen (inherited unchanged)

Targets adverse_mae/adverse_forward_3d (band 0.01); R1 (V2+sequence)
schema; miner N>=15, Δ>=0.02, top-5; permutation seed 20260926 +
shuffled null; hypothesis builder; validation logic. No new models,
targets, windows, features, or thresholds.
