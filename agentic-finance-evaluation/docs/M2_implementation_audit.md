# M2 Implementation and Audit Report (2026-09-26)

## 1. Question and scope

Can an ML model identify decision-time environmental conditions
associated with adverse decisions, under strict temporal and
point-in-time constraints? M2 separates the **representation question**
(V1 -> V2) from the **capacity question** (Logistic -> TabPFN) in a
pre-registered 2x2. The milestone ends at evaluator-side
`FailureHypothesis` objects. Nothing writes to MemoryStore; the agent,
runner, contracts, and validation semantics are untouched.

## 2. Verdict: M2-NULL (representation) / UNTESTED (capacity)

* **M2b (V2 x Logistic, primary `adverse_mae`): NULL.** VALID Brier
  0.3165 vs B0 0.2500; TEST 0.3501 vs 0.2500. Calibration FAIL on both
  held-out splits. Permutation TEST (0.3143) beats the model (0.3501).
* **M2b secondary (`adverse_forward_3d`): NULL.** VALID 0.3032 vs B0
  0.1958 (FAIL); TEST 0.1674 vs B0 0.2243 is a small-sample artefact:
  log-loss TEST 1.0557 vs B0 0.6431 (confident miscalibration),
  reliability top-bin 0.198 predicted vs 0.667 observed, and the top-10
  coefficient set is disjoint from the primary-target top-10
  (instability). Fails the both-splits generalisation rule.
* **M2a / M2c (TabPFN cells): BLOCKED-by-environment, NOT negative
  evidence.** `tabpfn==9.0.0` + `torch==2.14.0` install cleanly, but
  first use requires gated HuggingFace weights (`Prior-Labs/tabpfn_3_5`)
  plus `hf auth login`; this environment has no token, no HF cache, and
  no working network route (`TabPFNHuggingFaceGatedRepoError`,
  persisted verbatim in both cell artefacts). The capacity question is
  therefore **untested**, not answered.
* Missingness-only probe equals the prevalence baseline exactly
  (0.2500/0.2500 primary; 0.1958/0.2243 secondary): no missingness
  artefact this time — there is almost no missingness to exploit
  (only `rbi_stance`, 100% missing, correctly inert).
* Strongest allowable claim: "under the frozen temporal protocol, the
  richer V2 representation with logistic regression did not show
  temporally held-out information beyond prevalence; the TabPFN
  capacity comparison could not be executed in this environment."

## 3. Metrics (Brier primary; log-loss/reliability/AUROC/AUPRC secondary)

Primary target `adverse_mae` (TRAIN n=36 prev 0.50 / VALID n=36 prev
0.417 / TEST n=34 prev 0.735):

| split | B0 Brier | M2b Brier | perm Brier | miss-only | M2b AUROC |
|-------|----------|-----------|------------|-----------|-----------|
| VALID | 0.2500   | 0.3165    | 0.3253     | 0.2500    | 0.606     |
| TEST  | 0.2500   | 0.3501    | 0.3143     | 0.2500    | 0.698     |

Secondary target `adverse_forward_3d` (TRAIN n=32 prev 0.25 / VALID
n=30 prev 0.267 / TEST n=34 prev 0.324):

| split | B0 Brier | M2b Brier | perm Brier | miss-only |
|-------|----------|-----------|------------|-----------|
| VALID | 0.1958   | 0.3032    | 0.2795     | 0.1958    |
| TEST  | 0.2243   | 0.1674    | 0.4081     | 0.2243    |

(log-loss/AUROC/AUPRC/reliability per split persist in
`metrics.json`; TEST AUROC values on n=30-36 are reported without any
superiority claim.)

## 4. Frozen protocol compliance

* Splits TRAIN=E5A-1 / VALID=E5A-2 / TEST=E5A-3, never shuffled;
  `max(TRAIN ts) < min(VALID ts) < min(TEST ts)` asserted in code.
* No TEST contact during fitting; permutation seed 20260926,
  TRAIN-labels-only, VALID/TEST integrity flags all true.
* No new windows, no tuning (C=1.0 fixed), no target-picking (primary
  fixed before results), no agent/runner/MemoryStore changes.
* V1 semantics untouched; M1 control refit nowhere (re-read as control).

## 5. V2 feature provenance (23 frozen; PIT rule per feature in code)

Instrument x8 (`return_1/3/5/10d`, `volatility_10d`, `dist_high/low_20d`,
`volume_change_5d`, equity closes strictly < T); market x4 (Nifty 50
returns + vol, strictly < T); cross-market x3 (`usdinr_return_5d`,
`vix_change_5d`, `gold_return_5d` on GOLDAUG2023, no cross-contract
mixing); macro x4 (`rbi_policy_rate_pct` announcement-gated,
`rbi_stance`, `latest_cpi`/`latest_iip` availability-gated);
portfolio x3 (`drawdown` from same-episode decision-time snapshots,
`holdings_value`, `cumulative_costs`); context x1
(`active_context_version`, constant `C0-empty-store`, zero variance
documented). Missingness: zero everywhere except `rbi_stance`
(106/106 — pre-registered drop rule fires; retained as evidence, inert
in the model). V2 row identities are exactly the frozen V1 106 rows
(decision-id sets equal).

## 6. Leakage, reproducibility, stability checks

* `RETROSPECTIVE_OUTCOMES` guard raises on any outcome key in X (V1 +
  V2 builders); tmp-fixture tests assert strict-`<T` values,
  announcement/vintage gating, and schema exactness by hand computation.
* Forward-guard test: no `forward_*`, `mae/mfe`, `hold/opportunity`,
  future price/VIX/portfolio state in any feature payload.
* Reproducibility: two full `run_m2` executions give identical Brier
  numbers; M2a/M2c fingerprints byte-identical across runs
  (`7a19f560...`, `840bb0d4...`); M2b fingerprints stable after the
  persistence fix below (`4e2ff20d...`, `24e33290...`).
* Stability FAIL (part of the NULL verdict): disjoint top features
  across targets; n=36 TRAIN with ~50 columns (overparameterised by
  construction — reported, not fixed by tuning, per protocol).

## 7. Implementation notes (honest deviations, both fixed, no results seen first)

1. Persistence-gap fix: the first frozen run did not write the
   `model` block (coefficients/metadata) although the fingerprint
   covered it. Fixed `persistence.save_m2` to write `model.json`;
   re-ran with `--overwrite`. Metric values identical; fingerprints of
   the logistic cells changed once due to the added file and are stable
   since. Blocked-cell fingerprints never changed.
2. `requirements.txt` gains `tabpfn==9.0.0` + `torch==2.14.0`
   (actually installed and verified versions).

## 8. Files changed / added (for the commit gate)

* Added: `evaluation/attribution/features_v2.py`,
  `evaluation/ml/{__init__,diagnosis,evaluation,falsification,
  persistence,experiment}.py`, `evaluation/ml/models/{__init__,base,
  logistic,tabpfn}.py`, `scripts/run_m2.py`,
  `tests/ml/{test_v2_features,test_models,test_protocol}.py`,
  `docs/M2_implementation_audit.md` (this file).
* Modified: `requirements.txt` (2 dependency pins only).
* New evidence: `data/frozen_traces/_ml/e5a_combined_v2.json`,
  `data/frozen_traces/_m2/M2-20260926-{M2a,M2b,M2b_secondary,M2c}/`
  (7 files each for COMPLETE cells, 4 + manifest for BLOCKED cells).
* Deleted (approved, reference-checked): `E5A-smoke-*`, `E5A-repro-*`.
* Untouched (verified by diff): `agent.py`, runner, `TargetObservation`,
  `OraclePacket`, `environment/`, `evaluation/{contracts,baseline,
  context,diagnostics}/`, `MemoryStore`, `gate.py`, manifests,
  configs, V1 `features.py`, `m1_experiment.py`, frozen E5A windows,
  `scripts/run_e5_attribution.py`, `data/raw/*/source` gitlinks.

## 9. Experiment fingerprints

* M2a (BLOCKED): `7a19f56042d7214e640d8eb131c15046aadf240163f8e7efb32f9ebb9fe145fe`
* M2b (V2 x Logistic, adverse_mae): `4e2ff20d0875dd0a7f91a13895ff4992e871916d147e579cf7f01a3a85b047b0`
* M2b_secondary (adverse_forward_3d): `24e33290df741e1e0e659aab3751ac720684b28657880ff2694b9d780a40440e`
* M2c (BLOCKED): `840bb0d4fd4dc72934fa578c054d99c1ea3df895ab9f73ac2d6f3139074ed7cd`
* Model versions: scikit-learn 1.9.0, tabpfn 9.0.0 (blocked at
  weights), torch 2.14.0, numpy 2.5.2, pandas 3.0.5, Python 3.14.3.

## 10. Stop

No LearnedContext was created, no MemoryStore write occurred, no
repair rule was proposed. The repair pipeline stays shut until a
future cell demonstrates calibrated, generalising, permutation-
surviving signal — which M2 did not.
