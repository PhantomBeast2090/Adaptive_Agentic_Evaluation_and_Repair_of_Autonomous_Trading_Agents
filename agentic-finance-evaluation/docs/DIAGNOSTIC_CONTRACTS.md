# E2-A — Diagnostic Contract Layer

Status: representations for the adaptive diagnostic loop (milestone E2-A).
No selector, no executor, no inference, no LLM, no repair, no learning.

Package: `evaluation/diagnostics/contracts/`. Reuses frozen E0/E1 layers;
modifies nothing outside its own paths.

## Reused unchanged (deliberately not duplicated)

* E0 `Hypothesis` — the claim itself needed no wrapper: frozen, lifecycle,
  confidence, evidence refs, full fingerprint.
* E0 `DiagnosticTest` — covers test identity, typed+frozen intervention,
  measures, expected discrimination, cost, preconditions. Intervention
  provenance IS `DiagnosticTest.fingerprint()` (all fields included).
* E1 `MetricResult` — measured outcomes in results (value + explicit
  undefined reason, reused verbatim).
* E0 `EvaluationState` ordering gates (`record_test` before
  `record_test_result`, orphan/duplicate rejection) — mirrored, not forked.

## New contracts

* **HypothesisPrediction** — one falsifiable claim per (hypothesis, test)
  pair: observable, closed direction (`INCREASE|DECREASE|NO_CHANGE`),
  optional qualitative magnitude, confidence, rationale, method+version.
  Frozen at creation; pairs cannot be re-predicted (no moving goalposts).
* **DiagnosticTestResult** — what one execution observed: execution
  fingerprint, baseline reference (identity only — records never copied),
  intervention fingerprint (cross-checked against the registered test),
  the episode's own record/evidence refs, measured outcomes, adjudicated
  prediction ids, typed status (`COMPLETED|FAILED|INVALID`, error required
  unless completed), `outcome` (= status value, feeding E0
  `record_test_result` unchanged), provenance, full fingerprint.
* **HypothesisUpdate** — one assessed prediction/result encounter: full
  prior snapshot + verified prior fingerprint, prediction/result refs,
  `SUPPORTS|CONTRADICTS|INCONCLUSIVE` compatibility + assessment, full
  updated hypothesis with matching confidence, named method+version.
  Confidence is a recorded judgement, never a "posterior": method strings
  claiming Bayesian inference are rejected.
* **DiagnosticState** — append-only working memory: baseline refs, current
  hypothesis versions + registration ledger, predictions, available tests,
  results, update log, proposals, rationales, current uncertainty, budget
  usage (`tests` consumed), set-once stopping. Owns a fresh
  diagnostic-scope E0 `EvaluationState` mirroring registrations/results;
  the E1 artefact is referenced, never mutated. Enforces test →
  prediction → result → update ordering, stale-prior rejection
  (optimistic concurrency), and exact-replay consistency on load
  (stored ledger + history must reproduce stored currents and E0 mirror).
* **UncertaintySnapshot** — minimal current uncertainty: open hypothesis
  ids + assessing method + summary. History rebuildable from the log.
* **DiagnosticProposal / SelectionRationale / CandidateAssessment** —
  schema-constrained selector output: competing hypotheses, staked
  predictions, selected vs alternative tests, rationale reference,
  optional score (None = no fake precision), mandatory method+version.

## Invariants

Fail-closed typing; closed enums and closed `from_dict` field sets;
unique ids per scope; committed-before-executed ordering; prior-preserving
updates; set-once stopping; E0-mirror consistency verified on
deserialisation.

## Fingerprints

SHA-256 over canonical JSON of full payloads (`fingerprint_of_dict`).
IDs are caller-supplied deterministic strings (generation policy is
E2-B's job). No wall-clock, pids, or addresses anywhere in identity
(enforced by a source-level test plus determinism tests).

## Leakage

Diagnostic types (hypotheses, predictions, proposals, rationales, oracle
packets, plain dicts) are all rejected by the target-agent invocation
path; only E0 `TargetObservation` reaches agents. The contracts package
names neither the baseline artefact type nor the environment, so no code
path can mutate baseline records — enforced by test.

## What E2-A deliberately does NOT do

No hypothesis formation, no test selection/scoring, no intervention
execution, no inference engine, no repair, no validation, no learning, no
experiments, no failure labelling.
