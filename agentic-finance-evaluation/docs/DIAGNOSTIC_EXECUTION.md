# E2-B — Deterministic Diagnostic Intervention & Execution Engine

Status: controlled-experiment machinery (milestone E2-B). Non-adaptive.
No selector, no inference, no LLM, no repair, no learning.

Package: `evaluation/diagnostics/execution/`. Reuses frozen E0/E1/E2-A
layers and the untouched Indian environment; modifies none of them.

## 1. E2-B purpose

E2-B owns exactly one stage of the diagnostic loop: given an
already-registered `DiagnosticTest` and already-committed predictions, run
an isolated diagnostic episode of the target agent and register a
`DiagnosticTestResult`. It never judges hypotheses, ranks tests, or
interprets outcomes — it reports observations for later milestones.

## 2. Execution lifecycle

`execute(diagnostic_state, test_id, prediction_ids, target_agent,
episode_config)`:

1. Type checks; structural agent validation (`TypeError` on failure).
2. Test must be registered (`ValueError` otherwise).
3. `prediction_ids` non-empty, all committed, all belonging to `test_id`
   (`ValueError` otherwise).
4. Test budget exhausted → deterministic `ValueError` refusal (no run).
5. Execution fingerprint pre-computed; duplicate identity already recorded
   → `ValueError` before any execution.
6. Intervention materialised into a fresh environment config; unsupported
   content → recorded `INVALID` result (no episode run).
7. Unknown measure names → recorded `INVALID` result.
8. Fresh `IndianMultiAssetEnvironment` built; construction failure →
   recorded `INVALID` result.
9. Agent reset; episode driven decision-by-decision through E1's trusted
   observation path and `invoke_act`, with the environment as sole
   authority; per-decision failures → recorded `FAILED` result preserving
   legitimate records (metrics never fabricated).
10. Named measures computed from the episode's own records;
    `DiagnosticTestResult` built, registered with `DiagnosticState`, and
    returned inside a `DiagnosticEpisode` (result plus its own trajectory).

## 3. Intervention materialisation

E0's open `intervention` mapping is honoured, not replaced. Closed
supported set (`SUPPORTED_INTERVENTION_TYPES`):

* `null_intervention` — control arm under baseline market conditions;
  reproduces baseline mechanics bit-for-bit on identical scope.
* `transaction_cost_shift {multiplier}` / `transaction_cost_set
  {costs_bps}` — cost perturbation resolved against baseline costs.
* `vintage_policy_shift {vintage_policy}` — PIT resolution override.
  Strict PIT gating itself can never be relaxed by any intervention.
* `universe_restriction {nse_equity?, mcx_gold?}` — narrows the episode
  universe; named assets intersect episode scope, unnamed assets keep it.

Closed parameter sets per type (unknown parameters rejected, never
ignored); episode window must lie within the baseline grid; episode
universe must be a non-empty baseline subset. `DiagnosticTest.fingerprint()`
remains the canonical intervention specification identity.

## 4. Diagnostic episode isolation

Each execution builds a new environment and resets the agent; the E1
baseline artefact enters only as `(baseline_evaluation_id,
baseline_fingerprint)` references. Records live on the episode artefact,
never in baseline structures.

## 5. Execution fingerprint

SHA-256 over canonical JSON of: diagnostic/test ids, test and
intervention fingerprints, episode scope (window, universe, seed —
`base_dir` excluded as machine-specific provenance, mirroring
`Trajectory.content_digest`), agent id/version, baseline references, and
episode id. `episode_id = {diagnostic_id}:{test_id}:seed-{seed}`;
`result_id = R-{fingerprint[:16]}`. Same semantics → same identity; any
semantic change alters it. No clock, UUID, pid, or address anywhere
(source-scanned by test).

## 6. ID policy

Semantic derivation only: episode id from (diagnostic, test, seed);
result id from the execution fingerprint. No counters, no randomness.

## 7. Budget semantics

One execution consumes one `tests` unit (`tests_consumed` counts
registered results). `max_tests=0` or exhausted budget refuses with
`ValueError` before execution. `repairs`/`validation_runs` untouched;
`max_runtime` never wall-clock enforced.

## 8. Failure semantics

Caller errors raise (`TypeError`/`ValueError`). Semantic problems record
`INVALID` (unsupported intervention, unknown measures, bad scope, env
construction failure) with explicit reasons and no records. Mid-run
problems record `FAILED` with the exception text, preserved records, and
empty measures. `COMPLETED` carries full records and named measures.
Nothing is ever silently swallowed or fabricated.

## 9. DecisionRecord generation

Reuses E1's `_validation_entries` and `_build_record` (single
implementation, imported — not duplicated): observation identity,
visibility split, deep-frozen orders/validation/executions, env prices,
fees, portfolio snapshots, exact reward deltas, market fingerprint.

## 10. Measurement generation

E1 `compute_all` over the episode's own records, filtered to the test's
`measures` in declared order. Unknown measure names invalidate the test
before execution. No SUPPORTS/CONTRADICTS labelling — interpretation
belongs to `HypothesisUpdate` (later milestone).

## 11. Leakage boundary

Agents receive only `TargetObservation` via `invoke_act` (E1 trusted
path). Packets, states, tests, hypotheses, predictions, proposals,
results, dicts, and raw environment state are all rejected — adversarially
tested. No diagnostic metadata is added to observations; interventions
carry no future market outcomes (they only re-parameterise costs, vintage
resolution, universe, and window, all within PIT-valid mechanics).

## 12. Deterministic reproducibility

Same baseline, agent version, env spec, test, intervention, seed, and
execution config ⇒ identical trajectory and result fingerprint (tested by
double execution and by null-intervention reproduction of baseline
records). Nondeterministic agents are the caller's responsibility to
detect; the executor records what happened.

## 13. Baseline preservation

Baseline artefacts are hash-compared before/after episodes in tests;
results reference baseline identity without copying records.

## 14. Repeat-execution semantics

Option A (reject): exact-duplicate execution identity raises `ValueError`
pre-execution (E2-A duplicate rejection as backstop). Executions differing
in seed, agent, window, universe, or intervention are distinct episodes
with distinct fingerprints. Previous results are never overwritten.

## 15. What E2-B explicitly does NOT do

No test choice, scoring, or ranking; no hypothesis formation, update, or
confidence judgement; no Bayesian anything; no repair/validation/learning;
no LLM; no new metrics; no environment, calendar, PIT, or universe
changes.

## 16. How E2-C will consume E2-B later

E2-C (hypothesis updating / interpretation) will read `DiagnosticEpisode`
trajectories and registered results, compare measured outcomes against
committed `HypothesisPrediction` objects, and record `HypothesisUpdate`
entries — all through the already-frozen E2-A contracts, requiring no
executor changes.

    DiagnosticTest
          |
          v
    E2-B Executor
          |
       +--+----------------+
       |                   |
       v                   v
    Intervention       Fresh Episode
       |                   |
       +---------+---------+
                 |
                 v
          TargetObservation
                 |
                 v
             Agent.act()
                 |
                 v
          Environment.step()
                 |
                 v
          DecisionRecords
                 |
                 v
          Diagnostic Metrics
                 |
                 v
       DiagnosticTestResult
