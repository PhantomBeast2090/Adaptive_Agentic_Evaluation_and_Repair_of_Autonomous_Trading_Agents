# M-R4A — Loss-Chasing Power Benchmark: ACCEPT (first admitted repair)

CONTROLLED-KNOWN-MECHANISM. Protocol pre-registered in
`configs/controlled_repair/mr4a_protocol.yaml` (synthetic frozen feed,
explicit episode ranges, cap = normal size 5.0, seeds, tolerances).
Benchmark v1.1 (`benchmarks/loss_chasing_power.py`) reuses the frozen
loss-chasing-benchmark@1.0 agent on a deterministic sawtooth feed:
12-session repeat unit, 8 diagnostic blocks (96 sessions, 16 episodes) +
4 held-out blocks (48 sessions, 8 episodes). Base-only QA pre-freeze:
40/20 escalation sessions, counter resets after every episode, zero
cash-starved sessions.

## Results

Support 16/8 (≥10/5) with base excess > 0 in every counted episode.
Paired per-episode excess (repaired − baseline): diagnostic mean −37.5
CI [−46.25, −28.75]; held-out mean −37.5 CI [−50.625, −24.375]
(n_boot 5000, seed 20260930, α 0.05) — both below zero. Coverage 40
fires. Normal-session equality BASE==REPAIRED verified. `_decide`
ACCEPTED; tolerances pass (diag final 480.8k→491.3k, drawdown
0.039→0.018; held 496.7k→498.5k). No new validity issues; no inactivity.

## Admission, persistence, rollback

RepairProposal (provider loss-chasing row) → RepairResult ACCEPTED →
extract_candidate → adjudicate ADMITTED → MemoryStore.admit
(`store 721a99e0…`). Serving entry linked to admitted context;
verify_admission passes. Reload reproduces store, entry, behaviour, and
rule IDs exactly. Deactivation restores base behaviour exactly; policy
fingerprint preserved throughout (construction equality + twin
advancement proofs for the stateful policy).

## Verdict: ACCEPT — first scientifically admissible controlled memory
repair. Artefacts: `data/controlled_repair/MR4A-20260930/` (base traces,
verification, analysis, store, serving entry, audit chain
FEED_FROZEN→ROLLED_BACK, manifest). Wording fenced per §26: a controlled
known-mechanism demonstration of the repair architecture, not
natural-market discovery.
