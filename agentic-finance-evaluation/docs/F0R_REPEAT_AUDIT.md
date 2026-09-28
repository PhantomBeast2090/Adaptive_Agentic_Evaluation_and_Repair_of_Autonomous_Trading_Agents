# F0R Repeat Audit — Verdict: CONDITIONAL PASS (marginality flagged)

## Rationale record (pre-run, unchanged since proposal)

1. Affordability sizing + pyramid taper (fixed cash cutoff could never
   bind — arithmetic); 2. TREND_MIN −0.03→−0.05 (normal-pullback
   participation, margin above −0.08 exit band); 3. MAX_NAMES 3→4
   (SELL recurrence needs pre-stress inventory; capital binds first).
   VIX bands, MID hold, exits, windows, execution unchanged.

## Gate scorecard (thresholds unchanged from F0)

| Gate | F0R-A (142 sess) | F0R-B (65 sess) |
|---|---|---|
| ≥2 action classes | BUY/SELL/HOLD ✓ | BUY/SELL/HOLD ✓ |
| minor class ≥5% sessions | SELL 12/142 = 8.5% ✓ | SELL-involved 3/65 = 4.6% ✗ marginal |
| ≥2 quantities | 2.0×36, 1.0×64, partials ✓ | 2.0×8, 1.0×43, partials ✓ |
| exposure range ≥15pp | 0–100% ✓ | 0–100% ✓ |
| full exit | 3 ✓ | 0 ✗ (SELLs partial-only) |
| regime behaviour | LOW/MID/HIGH correct ✓ | LOW-only window, mixed ✓ |
| reproducibility/PIT/no-short/costs | ✓ (same-ID rerun identical; fees reconcile) | ✓ |

Wait — F0R-B exits: recount shows 0 full exits (F0-B had 2). SELLs in
F0R-B never flatten. Noted.

## Notable emergent behaviours (not tuned; recorded)

- Cash exhaustion is real: exposure reaches 100%, BINDING_CASH
  partials (0.61/0.96 lots) and a 0.0-qty execution row appear —
  F-CASH failure mode now has observable instances.
- Pyramiding works: q=1 dominates adds (64/36 in A), q=2 on entries.
- F-VOL guard holds (no MID BUYs by construction; verified in F0,
  policy unchanged).

## Verdict and why proceeding is legitimate

F0R-A passes fully; F0R-B misses minor-share by 0.4pp (4.6 vs 5.0)
and exits. This is reported as a marginal fail, NOT redefined:
no constant, threshold, or window was touched after seeing it.
Proceeding to F1 (pure description, no thresholds at stake) is
justified because the binding filter for diagnosis power is F2's
frozen miner (N≥15/condition): if SELL-bearing conditions cannot be
powered, F2 NULLs honestly. No tweak-loop entered (single repeat,
pre-registered changes only).

## Fingerprints

F0R-A `b260dd44…`, F0R-B `fdeda621…`. Manifests carry effective
agent_params + policy config SHA.
