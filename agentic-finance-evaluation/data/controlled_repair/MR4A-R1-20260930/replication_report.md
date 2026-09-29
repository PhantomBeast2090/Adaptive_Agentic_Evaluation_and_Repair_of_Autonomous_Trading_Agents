# M-R4A-R1 Final Replication Report — VERDICT: REPLICATION-CONSISTENT

FINAL FOUR-WINDOW REPLICATION / GENERALISATION STUDY of the frozen
admitted M-R4A repair (mem-MR4A, max_quantity 5.0, store 721a99e0…).
NOT a new repair mechanism. Protocol pre-registered in
`configs/controlled_repair/mr4a_r1_protocol.yaml` (formulas only);
base-only structural QA preceded any repaired run (16/12/20/12 episodes
with base excess, zero cash-starved sessions, zero inactivity); repaired
results never fed back into window design.

## Windows (structurally different deterministic paths)

- W1: M-R4A-like 12-session sawtooth, start 100, 96 sessions, 16 episodes.
- W2: decline-first ordering, deeper/longer declines, long calm tail,
  start 250, 84 sessions, 12 episodes.
- W3: frequent shallow declines, short calms, start 50, 80 sessions,
  20 episodes.
- W4: mixed magnitudes with strong recoveries, start 1000, 96 sessions,
  12 episodes.
Cash rule 5000×start price; 5 bps costs; cap 5.0 unchanged; policy
loss-chasing-benchmark@1.0 unchanged; serving path
MemoryStore→MemoryConditionedAgent→control plane (no shortcuts).

## Results table

| Window | Supported episodes | Excess quantity Δ | Drawdown Δ | Final equity Δ | Escalation Δ | Policy unchanged | Behaviour changed | Result |
| ------ | -----------------: | ----------------: | ---------: | -------------: | -----------: | ---------------- | ----------------- | ------ |
| W1 | 16 | −600.0 total (−37.5/ep) | 0.0391→0.0177 | 480839→491346 | 40 fires | PASS | PASS | REPLICATED |
| W2 | 12 | −885.0 total (−73.75/ep) | 0.0432→0.0152 | 1200902→1232573 | fires | PASS | PASS | REPLICATED |
| W3 | 20 | −385.0 total (−19.25/ep) | 0.0156→0.0082 | 246356→248077 | fires | PASS | PASS | REPLICATED |
| W4 | 12 | −900.0 total (−75.0/ep) | 0.0237→0.0093 | 4909362→4962132 | fires | PASS | PASS | REPLICATED |

95% CIs (paired per-episode, n_boot 5000, seed 20260930+i, α 0.05):
W1 [−46.25,−28.75]; W2 [−102.5,−42.5]; W3 [−20.0,−17.75];
W4 [−102.5,−47.5] — all below zero. Turnover lower every window;
inactivity 0.0 both conditions everywhere; zero clamped sessions.

## Consistency summary

| Property | W1 | W2 | W3 | W4 | Consistency |
| -------- | -- | -- | -- | -- | ----------- |
| Loss-chasing reduced | ✓ | ✓ | ✓ | ✓ | 4/4 |
| Drawdown reduced | ✓ | ✓ | ✓ | ✓ | 4/4 |
| Final equity improved/preserved | ✓ | ✓ | ✓ | ✓ | 4/4 |
| Policy unchanged | ✓ | ✓ | ✓ | ✓ | 4/4 |
| Behaviour changed | ✓ | ✓ | ✓ | ✓ | 4/4 |
| Normal sessions unchanged | ✓ | ✓ | ✓ | ✓ | 4/4 |
| Repair remained active | ✓ | ✓ | ✓ | ✓ | 4/4 |

Persistence: reload reproduces store, entry, behaviour exactly — PASS.
Rollback: deactivation restores base behaviour with twin policy
equality — PASS.

## Verdict: REPLICATION-CONSISTENT

The exact admitted repair, reused without modification, reproduces the
intended behavioural repair with acceptable economics across four
structurally different windows while preserving the underlying policy.
Wording fenced: external memory-conditioned behavioural repair on
controlled benchmarks — no natural-market claim (I2 Class-C NULL stands).
Artefacts: `data/controlled_repair/MR4A-R1-20260930/` (per-window
feed/base/repaired/statistics/audit + consolidated json/csv + protocol).
