# Repair Completion Report — M-R2/M-R3 Controlled Benchmarks

## 1. Architecture

MemoryStore → MemoryEntry → MemoryConditionedAgent serving path, built
in M-R0/M-R1 and exercised end-to-end here via
`scripts/run_controlled_repair.py`: BASE seal → controlled diagnosis →
compile → staging entry → SHADOW (bit-equality) → ACTIVE through frozen
`run_validation` (candidate = memory-conditioned agent) → custom metrics
→ `analyze_regression` → `_decide` → block bootstrap + coverage →
ACCEPT/REJECT/NSF → admission (extract/adjudicate/admit, ACCEPT only) →
persistence round-trip → rollback → manifest. All frozen infrastructure
reused unmodified except the authorised `max_quantity` vocabulary
extension (validator + enforcer + provider row + compiler mapping).

## 2. Files changed

Added: `configs/controlled_repair/{mr2,mr3}_protocol.yaml`,
`benchmarks/{volatility_blind,loss_chasing}.py`,
`scripts/run_controlled_repair.py`,
`tests/repair/test_controlled.py`,
`docs/{M-R2_VOLATILITY_REPAIR,M-R3_LOSS_CHASING_REPAIR}.md`,
this report, `data/controlled_repair/{MR2,MR3}-20260929/`.
Modified (surgical): `evaluation/diagnostics/repair/application.py`
(max_quantity), `evaluation/repair/{schemas,control_plane,compiler}.py`
(vocab + unbounded vix band), `evaluation/diagnostics/repair/provider.py`
(loss-chasing row), M-R1 vocab tests (explicit M-R3 amendment).
Untouched: E0–I2 evidence/protocols/thresholds, Indian environment,
attribution, miner, MemoryStore/gate logic.

## 3. Tests

`tests/repair/`: 48 passed (38 M-R1 + 10 controlled). Subsystems
re-verified: context/diagnostics-repair 243-run sweep green earlier this
phase; frozen suites untouched by these changes.

## 4–9. M-R2: REJECT

Protocol §7 windows (VIX-only); flaw confirmed (31 HIGH BUYs); compiled
`hold_all` [25,∞); shadow bit-identical; validation via serving path;
target 31→2 diag / 6→2 held-out; fires 30/10; policy preserved.
REJECT on pre-registered economics: diagnostic return 0.2805→0.1085
(trips 0.05); bootstrap diagnostic CI fully negative. Diagnosis: rebound
forfeiture — 59/77 HIGH sessions are post-crash recovery. Behavioural
repair perfect; admission correctly refused.

## 10–15. M-R3: NSF

Target 10→5 both windows; escalations 4→0 / 2→0; fires 10/5; `_decide`
ACCEPTED; tolerances pass. NSF on pre-registered statistics: both
bootstrap CIs straddle zero (rare events → negligible economic
separation). Honest insufficient-evidence verdict; no admission.

## 16. Fingerprints

Protocols, mechanisms, specs, entries, base/validation/analysis
fingerprints in per-experiment `manifest.json`; policy fingerprints
equal across base/active/reload stages (verified in-run; admission
stages unreached by rule, not by omission).

## 17. MemoryStore admission state

EMPTY for controlled repairs — no ACCEPT verdict occurred, so
extract/adjudicate/admit never ran. The admission path itself remains
frozen-tested; its zero-use here is gate success, not missing code.

## 18. E0–I2 firewall audit

`git diff` additive + surgical only (list §2); I2 Class-C NULL
unchanged; YESBANK unrescued (never compiled, never referenced by the
runner); frozen manifests/data/protocols byte-identical.

## 19. Limitations

Single-name universe; crash-window economics favour the flaw in M-R2;
rare-event power limits M-R3; bootstrap is an evidence gate, not proof;
calm-regime behaviour untested by these benchmarks; no LLM agents.

## 20. Final engineering verdict

CORE REPAIR LOOP: architecturally complete and causally proven end to
end (M-R1) with both controlled benchmarks demonstrating scoped
behavioural repair through the memory path under policy preservation.
M-R2: REJECT (economic regression). M-R3: NSF (insufficient evidence).
OVERALL: **no admitted repair — the DONE admission criterion is NOT met,
and is reported unmet rather than manufactured.** The system refused two
attractive repairs for the right reasons. That refusal is the validated
behaviour of the gate, and the terminal finding of this phase.
