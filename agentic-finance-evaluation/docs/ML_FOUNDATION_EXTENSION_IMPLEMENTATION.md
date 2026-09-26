# ML Foundation Extension — Implementation Report (2026-09-26)

## 1. Architecture

Additive, removable extension under `evaluation/ml/`; deterministic
core untouched. New: `models/{hist_gradient_boosting,timeseries_base,
chronos2,timesfm3,registry}.py`, `forecasting/{base,feature_adapter,
forecast_features}.py`, `diagnosis/{forecast_diagnostics,
conditional_miner,failure_hypothesis,hypothesis_builder,hypothesis}.py`,
`validation/ml_validation.py`, `scripts/run_mlf.py`,
`requirements-ml-foundation.txt`. One structural move: existing
`evaluation/ml/diagnosis.py` moved verbatim to
`evaluation/ml/diagnosis/hypothesis.py` (new `diagnosis/` package
shadowed the module; all frozen imports resolve unchanged through the
package `__init__`). `run_cell`'s `except TabPFNUnavailable` generalised
to the `ModelUnavailable` base (frozen-cell behaviour identical).

## 2. Model adapters

* **HGB** (`HistGradientBoostingClassifier`, fixed max_iter 200 /
  lr 0.1 / 31 leaves / seed 20260926, CPU): classical nonlinear
  control, no tuning.
* **Chronos-2** (`amazon/chronos-2`, rev `29ec3766d36d`, Apache-2.0):
  zero-shot univariate, q10/50/90, horizon 5, CPU. AVAILABLE (~1.1 GB
  RSS; fallback `chronos-2-small` authorised, not exercised).
* **TimesFM-3.0** (`google/timesfm-3.0-pytorch`, rev `43046b85ec22`,
  Non-Commercial v1.0, academic use): zero-shot, native (5,9)
  quantile matrix in documented level order, CPU. AVAILABLE
  (~1.7 GB RSS).
* Logistic (frozen control) and TabPFN (still BLOCKED-gated) unchanged.

## 3. PIT boundary

Forecast context = up to 256 closes strictly `< T` from frozen V2
loaders (no new pipeline). Proven: T+1 mutation leaves the input
fingerprint unchanged (test); short history raises and persists as an
UNAVAILABLE forecast row (missingness, never padding). Outcomes join
only in `forecast_diagnostics` (tagged EVALUATOR_ONLY); builders raise
on outcome keys.

## 4. Forecasting representation

`ForecastOutput` (frozen dataclass, unknown-field rejection,
output fingerprint) → 11 fixed derived features (q50 returns 1/3/5d,
5d tails, interval width, CDF-interpolated downside probability,
slope, curvature, dispersion, direction consistency; honest Nones).
Frozen config: horizons 1/3/5, q10/50/90, 256-bar context.

## 5. Diagnostic translation

`conditional_miner`: TRAIN-tercile bands frozen for VALID/TEST;
singles + pairs (TRAIN N≥15); candidate iff TRAIN Δ≥0.02 AND VALID
rate>VALID baseline; top-5; TEST reported only. `hypothesis_builder`
projects miner conditions onto the frozen `FailureHypothesis`
contract (lossy mapping documented; full `DiagnosticHypothesis`
persists alongside, born CANDIDATE).

## 6. Validation interface

`validation/ml_validation.py::validate_candidate` checks schema,
provenance, support, and action-neutrality; verdict is
ACCEPT_FOR_ADMISSION_REVIEW or REJECT with `admission:
NOT_PERFORMED`. Never imports MemoryStore/gate/extraction (AST-pinned
test). The existing gate was not modified and was not invoked.

## 7. Repair interface

No MemoryStore contact in this milestone (verified by test + diff).
Next authorised step (separate milestone): validated hypothesis →
`extract_candidate` → `gate.adjudicate` → `LearnedContext` →
admission → post-repair evaluation.

## 8. Experiment protocol

E5A-1/2/3 frozen splits; targets adverse_mae (primary) +
adverse_forward_3d (secondary, separate tables — a first-run
mislabel bug reusing primary labels for secondary cells was caught
and fixed before final persistence); zero-shot models; TRAIN-only
bands; seed 20260926; per-cell permutation; missingness probes;
no TEST tuning; no new windows; sequential model loading with
`release()` between runs.

## 9. Licensing

See `docs/ML_MODEL_LICENSES.md`. Chronos-2 Apache-2.0; TimesFM-3.0
Non-Commercial v1.0 (academic use documented); weights never bundled.

## 10. Computational limitations

Mac 8 GB: Chronos-2 120M fits (~1.1 GB), TimesFM-3.0 fits (~1.7 GB),
never resident simultaneously. CPU only. Two implementation bugs
found and fixed: volatile RSS in manifest fingerprint (moved to
unfingerprinted `environment` block) and the secondary-target label
reuse above.

## 11. Failure/blocked states

TabPFN: still BLOCKED_AUTHORIZATION (unchanged). No RESOURCE_LIMIT
hit. Miner: 0 candidates both models (diagnostic NULL, not a crash).

## 12. Reproducibility

Manifest fingerprints stable across reruns (chronos2 `4d86fc3a…`,
timesfm3 `6bee29d5…`); in-process forecast determinism True for both;
M3 numbers identical across runs. Provenance per run: code SHA, data
SHAs, checkpoint revisions, dependency versions, config, input/output
fingerprints, seed.

## 13. What remains untested

Multivariate/covariate Chronos-2; ensemble; any MemoryStore admission
or post-repair evaluation; regime expansion beyond E5A-1/2/3.

## 14. Results and interpretation

| cell | VALID Brier (B0→M) | TEST Brier (B0→M) | verdict |
|---|---|---|---|
| M3 primary | 0.2500→0.3601 | 0.2500→0.2242 | NULL (VALID fails) |
| M3 secondary | 0.1958→0.2842 | 0.2243→0.1796 | NULL (VALID fails) |
| Chronos2→logistic primary | 0.25→0.2884 | 0.25→0.5086 | NULL |
| Chronos2→logistic secondary | 0.1958→0.3678 | 0.2243→0.2919 | NULL |
| TimesFM3→logistic primary | 0.25→0.2732 | 0.25→0.3955 | NULL |
| TimesFM3→logistic secondary | 0.1958→0.254 | 0.2243→0.279 | NULL |

Permutation beats or matches models on held-out splits throughout;
missingness probes equal baseline. Forecast directional agreement
0.57/0.52 (secondary only). Miner: no TRAIN band confirmed on VALID
for either model → zero hypotheses → nothing reached validation.
** milestone verdict: infrastructure COMPLETE and executable;
diagnostic signal NULL on this sample. ** The TEST-only gains repeat
the M1/M2b small-sample family; no profitability, repair, or
generality claimed. MemoryStore untouched (NO); agent code unchanged
(NO).

## 15. Exact next milestone

Authorise a repair-loop milestone ONLY if a future representation
produces a validated (accepted-for-review) hypothesis; otherwise the
honest programme is sample/regime expansion under a pre-registered
single-expansion contract, not more models.
