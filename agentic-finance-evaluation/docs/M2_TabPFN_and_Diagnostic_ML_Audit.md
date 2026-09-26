# M2 TabPFN and Diagnostic ML Audit (2026-09-26, continuation)

## 1. Repository state

* HEAD at session start: `33a2532` (M2 artefacts); parent `b5ea944`
  (M2 code/tests/docs). Worktree contained only the two pre-existing
  `data/raw/{convfinqa,finqa}/source` gitlink modifications; untouched.
* M2 implementation audited as-is: `evaluation/ml/` (models/base,
  logistic, tabpfn adapter; diagnosis, evaluation, falsification,
  persistence, experiment), `evaluation/attribution/features_v2.py`
  (23 frozen features), `scripts/run_m2.py`, `tests/ml/` (18 tests),
  `_m2` cells + `_ml` combined datasets. No architectural changes were
  made in this session; no frozen file was modified.
* Post-audit test status: `tests/ml` + `tests/attribution` 46/46 pass.
  Frozen paths (`environment/`, `evaluation/{contracts,baseline,
  context,diagnostics}/`, `configs/`, manifests, agent, runner,
  MemoryStore, E0–E5A evidence) verified untouched via diff.

## 2. TabPFN dependency resolution: M2-TABPFN-BLOCKED

No code or protocol change unblocks this; the blocker is a
human-gated licensing step outside the repository:

* `tabpfn==9.0.0` + `torch==2.14.0` installed (pinned, verified).
* `Prior-Labs/tabpfn_3_5` weights are gated: first `.fit()` requires a
  Prior Labs API key (`TABPFN_TOKEN`, license accepted at
  ux.priorlabs.ai). No key, no HF token, and no HF cache exist in this
  environment.
* Network diagnosis (new evidence): raw TLS to huggingface.co fails on
  system certs, but succeeds with the venv's certifi bundle
  (`HF API status: 200`, repo metadata confirms `private:false`,
  `license:other`). Transport is therefore solvable; **authorization
  is not** — it requires a human to register, accept terms, and issue
  a key. No unofficial mirror was used (not reproducible, not
  licensable).
* `availability_probe()` reports the gated-auth failure without
  touching research data — exactly the designed graceful-skip path.

## 3. Exact model/version

* Package `tabpfn==9.0.0`, `torch==2.14.0`, `scikit-learn==1.9.0`,
  `numpy==2.5.2`, `pandas==3.0.5`, Python 3.14.3, CPU backend,
  `random_state=20260926`, default ensemble
  (`n_estimators='auto'`, `fit_mode='fit_preprocessors'`).
* Weight identifier: `Prior-Labs/tabpfn_3_5` (gated, not obtained).
  Citation recorded in `evaluation/ml/models/tabpfn.py` as an external
  tool, not a contribution.

## 4. Weight provenance

Not obtained. Gated repository; terms unaccepted; no key issued.
M2a/M2c cell artefacts persist the verbatim
`TabPFNHuggingFaceGatedRepoError` plus probe evidence under
`data/frozen_traces/_m2/M2-20260926-{M2a,M2c}/` (fingerprints
`7a19f560...`, `840bb0d4...`, byte-identical across reruns).

## 5. Experiment configuration (frozen, unchanged)

TRAIN=E5A-1 / VALID=E5A-2 / TEST=E5A-3; primary `adverse_mae`,
secondary `adverse_forward_3d`; V1/V2 schemas, TRAIN-only
preprocessing, seed 20260926, C=1.0 logistic; Brier primary with
log-loss/reliability/AUROC/AUPRC secondary; per-cell permutation;
temporal-order assertion; no TEST contact during fitting.

## 6. M2a results (V1 x TabPFN)

BLOCKED — no predictions, no metrics; blocker evidence persisted.
Not a failure; the capacity comparison is unexecuted.

## 7. M2c results (V2 x TabPFN)

BLOCKED — same status and evidence as M2a.

## 8. Permutation results (recap, unchanged from M2 audit)

* M2b primary: perm VALID 0.3253 / TEST 0.3143 vs model 0.3165/0.3501
  (permutation beats the model on TEST).
* M2b secondary: perm VALID 0.2795 / TEST 0.4081 vs model 0.3032/0.1674
  (model worse than permutation on VALID). Integrity flags all true.

## 9. Leakage audit

* V1/V2 builders raise on any `RETROSPECTIVE_OUTCOMES` key in X;
  tmp-fixture tests verify strict-`<T` bars, announcement-gated RBI,
  availability-gated CPI/IIP by hand computation.
* V2 row identities exactly equal frozen V1 106 rows. No future price,
  VIX, MAE/MFE, or portfolio state enters any feature. Oracle boundary
  intact; agent reads unchanged (3 leaves).

## 10. Reproducibility audit

* Two full `run_m2` executions: identical Brier numbers; M2a/M2c
  fingerprints byte-identical; M2b fingerprints stable post-fix
  (`4e2ff20d...`, `24e33290...`).
* 46/46 `tests/ml`+`tests/attribution` pass post-audit.
* TabPFN cells are reproducibly blocked (deterministic probe +
  fingerprinted blocker evidence), which is itself a stable result.

## 11. Comparison with B0/M1/M2b

B0 (prevalence) remains unbeaten on every VALID split across M1, M2b
primary, and M2b secondary. M2b primary repeats the M1 pattern (held-out
calibration worse than constant; permutation competitive). The V2
representation did not rescue logistic regression — the failure
localises to sample/regime, not (only) to features.

## 12. Scientific verdict: M2-TABPFN-BLOCKED; M2-NULL stands

Per §5 categories: not M2-INFORMATIVE (no criterion met), not a TabPFN
failure. Overall position: **M2-NULL (representation) /
M2-TABPFN-BLOCKED (capacity).** No claim about model capacity is made.

## 13. Bottleneck diagnosis (evidence-backed, paper-central)

* **A. Sample size — PRIMARY.** TRAIN n=36 (primary) with ~50
  preprocessor columns: logistic is overparameterised by construction;
  VALID underperforms a constant. Nothing can be concluded about
  features or capacity until n≫p or p is cut by pre-registered rule.
* **B. Regime diversity — SECONDARY.** Three windows, adverse_MAE
  prevalence 0.50→0.42→0.74; the unused high-VIX window (18/18
  NO_ORDERS) was correctly excluded, leaving only calm/low-rate-cut
  regimes. Temporal generalisation is untestable, not just failed.
* **C. Representation — NOT EXONERATED, NOT CONVICTED.** V2 adds real
  PIT-valid structure (returns, vol, drawdown, vintage macro), but with
  n=36 no representation can separate signal from fit noise.
* **D. Target formulation — TOO CRUDE FOR REPAIR.** `adverse_MAE` is a
  binary retrospective excursion flag; primary vs secondary targets
  produce disjoint top features. Scalar P(adverse) cannot name a
  condition to repair.
* **E. Model capacity — UNTESTED.** No evidence either way.
* **F. Unstable context-outcome relationship — SUPPORTED.** Prevalence
  swings + disjoint coefficients across targets are consistent with
  nonstationarity; any future claim needs cross-window support rules.
* **G. Translation to repair hypothesis — MISSING LAYER.** M2 ends at
  scalar probabilities + unstable coefficients; there is no designed
  path from these to `failure_mechanism / corrective_principle /
  applicability_conditions`. This is the next milestone, not a tuning
  problem.

## 14. Recommendation: Diagnostic ML (DESIGN ONLY — not implemented)

New additive package `evaluation/ml/diagnosis/` (distinct from the
existing `diagnosis.py` hypothesis object, which it consumes):

* **Condition miner (pre-registered grid only):** single-feature bands
  (e.g. terciles of each numeric V-feature + instrument identity)
  scored as conditional adverse rate vs applicable baseline, with
  N/counts, per-window rates, and a temporal-support rule (same
  direction in ≥2 windows, never TEST-selected). PIT-safe by
  construction — inputs are decision-time features only.
* **Effect object `ConditionalFailureRate`:** condition, N/k/rate,
  baseline rate, delta, windows supported, calibration snapshot,
  model/dataset fingerprints. Maps 1:1 onto `FailureHypothesis`
  (mechanism = "elevated adverse rate under X",
  applicability_conditions = X, evidence = the rate table).
* **LearnedContext mapping:** miner output feeds existing
  `extract_candidate` conventions; corrective principles are proposed
  as reviewable templates (never auto-admitted); `gate.adjudicate`
  and MemoryStore admission remain the sole authority. ML never
  admits itself.
* **Falsification retained:** permutation, prevalence-shift check,
  missingness audit, and the deterministic E5A NULL as a tripwire —
  any miner "discovery" contradicting none but supported by nothing
  is reported NULL.
* **Prediction vs diagnosis (§10):** scalar risk is retained for
  scoring, but repair consumes only conditional, temporally supported
  rate differences. No silent target change: `adverse_MAE` stays the
  scoring target; the diagnostic layer adds conditional views.
* **E5A NULL (§11) stays intact:** bands are pre-registered, not
  reverse-engineered; an empty miner result is a publishable NULL.

## 15. Explicit statement

No repair was performed. No LearnedContext was created. Nothing was
written to MemoryStore. The agent, its observations, the runner, and
all validation/admission semantics are unchanged. No trading
instruction was produced; profitability was not optimised, measured,
or claimed.

## 16. Provenance of this report

Session: M2 continuation, build mode. One new file (this report); zero
code/evidence modifications (verified by `git status`/`git diff`).
Prior fingerprints and verdicts quoted verbatim from persisted
artefacts, not recomputed.
