# M4 Sequence-Feature Implementation (2026-09-26)

## 1. What was built

`evaluation/attribution/features_seq.py` (new, additive; V1/V2
untouched): 24 frozen sequence features over trailing k=3/5 windows
of the frozen `baseline_result.json` trajectory order. For an EXECUTED
row matched to record index `i` (same timestamp+order join as V1/V2),
history = records[0:i] — strictly earlier, never current, never later.

Families: A. action history (`seq_n_prev`, `seq_buy_count`,
`seq_exec_freq`, `seq_action_persistence` — dominant-side share vs the
current decision's own side); B. exposure (`change/mean/slope`);
C. cash (`change/min`); D. portfolio (`equity/realized change`);
E. prior realised rewards (`mean`). Every feature has provenance
(source field, trajectory, cutoff, window, observability,
missingness, formula) in `SEQ_PROVENANCE`. Short history aggregates
over what exists; zero history stays None.

R1 = frozen V2 rows + V3 merge on `decision_id`
(`data/frozen_traces/_ml_sequence/e5a_combined_v3.json`); R0 reruns
V2 in the identical code path (reproduces M2b/M3 numbers exactly,
validating the harness). `scripts/run_m4.py` runs R0/R1 ×
Logistic/HGB × both targets via unchanged `run_cell` (permutation +
missingness probes free). `persistence.save_m2` gained a
backward-compatible `subdir` parameter (`SEQUENCE_SUBDIR`).

## 2. Rationale for prior rewards

Prior records' realised rewards occurred strictly before T and are
derivable from portfolio snapshots the agent itself observes; they
are legitimate history. The current record's reward never enters X
(proven by the outcome-mutation test).

## 3. Leakage tests (all pass)

`tests/ml/test_seq_features.py` (4 tests): frozen 24-allowlist +
outcome exclusion; hand-computed values and support honesty
(`seq_n_prev_k3=2.0` with 2 priors — no invention); T+1 trajectory +
future-outcome mutation leaves d1 features byte-identical; current
reward/outcome mutation leaves d2 history features byte-identical.

## 4. Frozen artefacts

`data/frozen_traces/_ml_sequence/`: `e5a_combined_v3.json` + 8 cells
(R0/R1 × logistic/hgb × primary/secondary), each with
config/metrics/model/predictions/hypotheses/permutation/manifest.
R0 fingerprints differ from M2b/M3 only by cell_id/config (same
metric values — exact reproduction).

## 5. What was NOT done

No agent/MemoryStore/TargetObservation/validation changes; no new
models, windows, or targets; no tuning; no repair; no MemoryStore
writes. `requirements.txt` untouched.
