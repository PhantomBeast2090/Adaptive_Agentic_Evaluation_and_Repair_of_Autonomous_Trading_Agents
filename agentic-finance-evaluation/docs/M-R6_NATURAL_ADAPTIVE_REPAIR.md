# M-R6 — Natural Indian-Market Adaptive Repair: NULL (honest negative)

## Verdict

**NULL — NATURAL-MARKET-REPAIR-NULL: no admissible repair.**
No MemoryStore write. No held-out construction. No replication.

## What ran

Frozen MultiAssetChoice (g1.yaml, 6-name NSE universe) on real Indian
data, diagnostic 2020-01-01..2020-06-30 (123 sessions: 104 HOLD, 9 BUY,
7 SELL, 3 MIXED). Windows pre-registered from VIX prevalence only.
Trajectory adapter derived PIT-safe fields exclusively (timestamp,
order sides/quantities, counts, pre-decision portfolio snapshot,
realised step reward, peak-tracked drawdown, as-of VIX); retrospective
legs refused by construction (unit-tested, AST-audited).

## Detection (outcome-blind)

All five detectors ran; two fired:
- exposure: support 46, severity 3.0 (breadth accumulation to 6 names)
- overtrading: support 18, severity 3.0
- loss_chasing / volatility / drawdown: None (abstentions recorded)

Pre-registered multi-rule (support, then severity, then id) selected
**exposure**. 9 candidates generated, 0 refused at compile; all 9
evaluated through the real MemoryConditionedAgent serving path
(shadow equality asserted per candidate).

## Why every candidate was rejected

Falsification battery (frozen adjudication):
- max_quantity {4,5,6}: bootstrap CI includes null (upper == 0.0) +
  normal-session alteration → REJECT.
- exposure_cap {1,2}, quantity_reduction {0.25,0.5},
  per_session_order_cap {1,2}: CIs exclude null and economics
  improved — but all altered protected calm-session behaviour →
  REJECT under the pre-registered normal-preservation rule.

The binding constraint is substantive, not technical: the diagnosed
breadth accumulation occurs substantially in calm (VIX ≤ 25) sessions,
so any breadth discipline necessarily fires there, while the frozen
normal definition protects calm sessions. The two pre-registered
specifications genuinely conflict on this mechanism; the fail-closed
gate refused admission. No threshold was moved; no window reselected.

## Negative controls (all refused/rejected, recorded in controls.json)

- Opposite-side block (SELL): refused at family eligibility.
- Unscoped hold_all: refused at compile (UNCOMPILABLE).
- Total suppression (order_cap 0): REJECTED by inactivity guard.

## Frozen audit

E0–I2 artefacts, protocols, thresholds, I2 Class-C NULL, YESBANK status:
all untouched (see final report diff). M-R2/M-R3/M-R4/M-R5 artefacts
untouched. No MemoryStore write exists for M-R6.

## Interpretation

The adaptive repair machinery (M-R5) works on natural trajectories —
detection, synthesis, compilation, shadow, serving, adjudication all
executed — but produced no admissible repair. The natural track
therefore remains what I2 found: no validated failure mechanism with
an admissible memory repair. The open design question this exposes is
mechanism-relative vs regime-relative normality, stated here as a
finding for future protocols, not as a change to this one.
