# M-R4 Completion Report

## Repository state

Branch main; M-R4 commits on top of 8690e5d (M-R2/M-R3). New additive
files only, plus two surgical authorised edits (drawdown trigger field;
twin-semantics assertion fixes in runners).

## Benchmark versions

- M-R4A: loss-chasing power v1.1 (synthetic frozen feed, 16+8 episodes),
  agent loss-chasing-benchmark@1.0 reused unchanged.
- M-R4B: M-R4-controlled-volatility-drawdown (Indian env, same windows as
  M-R2, drawdown-gated hold_all). M-R2 REJECT stands under its version.

## Protocol fingerprints

`mr4a_protocol.yaml` / `mr4b_protocol.yaml` hashed into every manifest;
feed fingerprint `FEED_FROZEN` audit event; episode ranges explicit.

## Mechanisms & repair principles

- M-R4A: post-loss escalation 5·2^n → max_quantity{5.0} (binds only
  escalation; normal flow provably untouched).
- M-R4B: high-VIX accumulation while underwater → hold_all scoped
  [25,∞) with (vix>25 ∧ drawdown>0.05) trigger.

## Diagnostic / held-out splits

- M-R4A: sessions [0,95] / [96,143] frozen feed segments.
- M-R4B: 2020-01-01..2020-06-30 / 2022-01-01..2022-06-30 (same as M-R2).

## Support

- M-R4A: 16 diag / 8 held episodes with base excess > 0 (≥10/5 ✓).
- M-R4B: 53 fires (≥10 ✓).

## Primary metric / effects / CIs

- M-R4A mean episode excess: diag −37.5 [−46.25,−28.75]; held −37.5
  [−50.625,−24.375] (paired bootstrap, n_boot 5000, seed 20260930).
- M-R4B high-VIX buys: 31→25 diag; 6→6 held-out.

## Bootstrap configuration

Paired (M-R4A per-episode) / block-5 (M-R4B per-session rewards), 2000–
5000 samples, α 0.05, seeds 20260929/20260930 (+1 held-out). CI = evidence
gate, never proof.

## Economic / regression checks

- M-R4A: final +10.5k diag / +1.8k held; drawdown improved both splits;
  turnover/inactivity/validity clean.
- M-R4B: return −0.117 diag (trips 0.05); held neutral.

## Admission decisions

- M-R4A: `_decide` ACCEPTED → extract → adjudicate ADMITTED →
  MemoryStore.admit (store `721a99e0…`). FIRST ADMITTED REPAIR.
- M-R4B: `_decide` REJECTED → no admission (correct refusal).

## Memory / policy / behaviour fingerprints

M-R4A: policy equal at construction + twin-equal post-run; memory
admitted (store fp above); behaviour differs exactly on escalation
sessions; normal sessions bit-identical. Reload reproduces store, entry,
behaviour, rule IDs. Rollback restores base behaviour exactly.

## Persistence / rollback

M-R4A: REPRODUCED / RESTORED (asserted, fingerprinted). M-R4B:
NOT_ATTEMPTED (by rule — no admission).

## Frozen E0–I2 audit

Additive-only diff; I2 Class-C NULL intact; YESBANK unrescued and
unreferenced; frozen data/manifests/protocols byte-identical; M-R2/M-R3
verdicts unchanged (rerun determinism confirmed for M-R2).

## Verdicts

- M-R4A: ACCEPT — first scientifically admissible controlled memory repair.
- M-R4B: REJECT — refined trigger does not rescue volatility-suppression
  economics; reported separately, no further variants.
