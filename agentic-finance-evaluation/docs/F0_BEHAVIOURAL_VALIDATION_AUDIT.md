# F0 Behavioural-Validation Audit — Verdict: GATE NOT MET (STOP)

## 1. Files changed

Added: `agents/choice/policy.py` (+`__init__.py`), `configs/choice_agent/
f0.yaml`, `scripts/run_f_agent.py`, `tests/agents/
test_choice_accumulator.py`, `data/frozen_traces/F0-A-20260926/`,
`data/frozen_traces/F0-B-20260926/` (baseline_config, environment_
spec, baseline_result, manifest each), this report. Modified: none.

## 2. Frozen files verified untouched

`environment/`, `evaluation/{contracts,baseline,context,diagnostics}/`,
`benchmarks/`, `configs/indian_environment.yaml`, E0–E5A/M1–M4
evidence, TargetObservation/OraclePacket/MemoryStore/gate semantics —
confirmed via `git diff` (only additive paths differ). `configs/`
gains one new file; zero frozen bytes altered.

## 3. Frozen policy constants

VIX_LOW 15.0, VIX_HIGH 25.0, TREND_LOOKBACK 5, TREND_MIN −0.03,
TREND_SELL −0.08, BUY_Q {2 if cash≥20000 else 1}, SELL_Q 2,
instruments RELIANCE/TCS/INFY, MAX_NAMES 3, MAX_NAME_COST 60000,
CASH_DUST 1000, MAX_ORDERS 3. In `agents/choice/policy.py`,
mirrored in `configs/choice_agent/f0.yaml` (test asserts equality),
fingerprinted in both manifests.

## 4. Fingerprints

F0-A (`82efd790…`, 142 records, 2019-11-01→2020-05-29);
F0-B (`6e89a8af…`, 65 records, 2023-05-15→2023-08-14). Same-ID rerun
of F0-B reproduces bit-identically (an apparent mismatch during the
audit traced to a different experiment id, not nondeterminism).

## 5. Action distribution

F0-A sessions: HOLD 136 / BUY 3 / SELL 3. F0-B: HOLD 59 / BUY 4 /
SELL 1 / BUY+SELL 1. All executions EXECUTED_FULL; submitted ==
executed (no silent drops).

## 6. Quantity distribution

Only 2.0 (12 F0-A, 11 F0-B executions). CASH_FULL=20000 never binds
at 100k capital with ≤3-name exposure — design flaw, visible a
priori, NOT fixed (would be outcome-tuning).

## 7. Exposure range

Holdings/equity: F0-A 0.000–0.169 (16.9pp ✓), F0-B 0.000–0.421
(42.1pp ✓).

## 8. SELL/exit statistics

F0-A 6 SELL / 3 full exits; F0-B 3 SELL / 2 full exits (position-key
disappearance handled). Zero negative positions (no-short holds).

## 9. VIX-regime behaviour

F0-A: LOW→BUY/HOLD, MID (36 sessions)→HOLD with zero BUY violations
(F-VOL guard integrity holds — per protocol this is implementation
evidence, not a mined mechanism), HIGH→SELL/HOLD. F0-B entirely LOW
with mixed BUY/SELL/HOLD.

## 10. Test results

10/10 new unit tests pass (regimes, trend buffer, sizing, caps,
exits, determinism, adapt surface, config-constant parity).
Cost identity: execution-fee sums match `transaction_cost_total`
exactly (15.2217 / 28.3481). BINDING_* honestly absent (no partials;
frozen env tests cover the path).

## 11. Implementation defects discovered

None affecting validity. Two audit artefacts, both resolved with
evidence: (a) exit detection must treat disappearing position keys
as flat (fixed in audit script, not policy); (b) apparent
rerun-mismatch was experiment-id inclusion in the fingerprint.

## 12. Gate verdict (pre-registered thresholds)

PASS: action classes, exposure range, full exits, regime behaviour,
reproducibility, PIT integrity, no hand-coded failure, no-short,
BINDING honesty, cost identity. FAIL: minor-class session share
(2.1% / 3.1% vs 5%), quantity diversity (1 value vs 2).
Partial-fill path unexercised (no verdict possible).

## 13. Diversity sufficiency for F1

**NOT established — STOP.** Total non-HOLD executions ≈ 23 across
both windows with a single quantity; F2-style mining (N≥15 per
condition) cannot be powered, and any F1 attribution would inherit
the same sparsity the M-series already exhausted. Per §18/§26 the
stopping rule triggers: no attribution, no repair, no ML follow-on.

Remediation (separately authorised F0-repeat only, new experiment
id, design-rationale-first): scale CASH_FULL to capital so sizing
varies; rebalance SELL_Q/accumulation so exits recur; relax the
trend-initiation rule on documented (not fitted) grounds; consider a
third window only under a pre-registered regime contract. Constants
in this run stay frozen as the NULL record.
