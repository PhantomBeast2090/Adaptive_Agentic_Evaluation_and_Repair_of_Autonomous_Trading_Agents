# E2-C — Deterministic Hypothesis Interpretation

Status: interpretation of executed diagnostic evidence (milestone E2-C).
No test selection, no inference engine, no LLM, no repair, no learning.

Package: `evaluation/diagnostics/interpretation/`. Reads frozen E0/E1/E2-A
contracts and the frozen baseline artefact; modifies nothing outside its
own paths and writes only through `DiagnosticState` ordering rules.

## 1. E2-C purpose

Turn one registered COMPLETED `DiagnosticTestResult` plus its committed
`HypothesisPrediction` objects into one `HypothesisUpdate` per prediction
plus a fresh `UncertaintySnapshot` — deterministically, independently per
rival, without ranking, without Bayes, without executing anything.

## 2. Input/output contracts

In: `DiagnosticState` (working memory), `result_id` (registered result),
`prediction_ids` (committed predictions), `BaselineResult` (frozen
control, read-only). Out: `InterpretationRecord` handle (update ids,
snapshot id, method/version, fingerprint); updates and snapshot recorded
in state. Caller errors (unknown result, non-COMPLETED status, uncommitted
or mismatched predictions, baseline identity mismatch, double-counted
pairs, stale versions) fail before any update is created.

## 3. Comparison methodology (`directional-band v1`)

Relative change `r = (obs − base) / |base|` against materiality band
τ = 0.01: `INCREASE` iff `r > τ`; `DECREASE` iff `r < −τ`; `NO_CHANGE`
iff `|r| ≤ τ`. Zero control uses exact comparisons (counts/rates at exact
zero are exact). Directional claims falling outside their region —
including inside the band — are `CONTRADICTS`. Either side missing or
explicitly undefined yields `INCONCLUSIVE` with the recorded reason; the
method never distinguishes what the evidence cannot distinguish.
Prediction free-text magnitude is rationale, never parsed.

## 4. Treatment of missing observations

Absent metric in result, undefined metric in result, absent metric in
baseline, undefined metric in baseline → `INCONCLUSIVE` with an explicit
reason naming the side and the recorded undefined-reason. Never
fabricated, never silent `CONTRADICTS`.

## 5. SUPPORTS / CONTRADICTS / INCONCLUSIVE semantics

Compatibility of one directional claim with one observation — not a
verdict on the hypothesis, not a ranking, not a probability. Rivals
sharing a test each receive their own assessment from the same observed
value.

## 6. Confidence transition methodology

Bounded symmetric steps: SUPPORTS +0.10, CONTRADICTS −0.10,
INCONCLUSIVE 0.0, clamped to [0, 1]. Documented conventions stamped with
method/version on every update — not priors, likelihoods, or posteriors
(the update contract rejects Bayesian wording by validation).

## 7. Lifecycle transition methodology

Conservative ladder: INCONCLUSIVE preserves; SUPPORTS moves
PROPOSED→UNRESOLVED, UNRESOLVED→SUPPORTED, WEAKENED→UNRESOLVED,
SUPPORTED→SUPPORTED; CONTRADICTS moves PROPOSED/UNRESOLVED/SUPPORTED→
WEAKENED, WEAKENED→REJECTED; REJECTED is terminal. Single observations
never jump to endorsement or rejection. Updated evidence refs extend
prior refs with the result fingerprint, order-preserving.

## 8. Competing hypothesis handling

Each prediction is assessed alone against the same observation; update
ids, confidences, and statuses are per-hypothesis. No shared verdict, no
scoreboard, no "winner" field exists anywhere in the artefacts.

## 9. Sequential update handling

Updates append; priors are preserved in full; `record_update` rejects
stale prior fingerprints; re-interpreting an already-covered
(prediction, result) pair is refused so evidence is never double-counted.
Current versions always derive from the assessed prior.

## 10. Uncertainty snapshot

Minimal, current-only: open ids (statuses PROPOSED/UNRESOLVED/WEAKENED,
sorted), deterministic templated summary, method/version, deterministic
assessment id. No distributions, no rankings, no best hypothesis.

## 11. Deterministic identity

SHA-256 over canonical JSON of full payloads; caller-supplied
deterministic ids (`{result}:{prediction}:u{n}`,
`{diagnostic}:ua:{result}`, `{diagnostic}:interp:{result}`); methodology
constants feed fingerprints via method/version fields and assessment
text. No clock, UUID, pid, randomness (source-scanned by test).

## 12. Failure semantics

Contract failures raise (missing/unregistered result or predictions,
non-COMPLETED status, test mismatch, foreign baseline, double-count,
stale prior). Evidence gaps record INCONCLUSIVE. Execution NEVER happens
here — E2-C imports no environment, market, or data modules
(source-scanned by test).

## 13. Leakage boundaries

Only `TargetObservation` ever reaches agents (E0 boundary, re-verified by
regression gates). E2-C adds no observation path at all: it reads result,
prediction, and baseline artefacts, which never flow toward any agent.

## 14. Explicit exclusions

No test selection/ranking/proposals, no hypothesis formation, no Bayesian
or other inference, no repair/validation/learning, no environment access
or re-execution, no new metrics, no market data loading (suite runs in
~0.5s), no frozen-file modifications.

## 15. E2-D handoff

E2-D (adaptive selection) consumes: `DiagnosticState.hypothesis_updates`
(history), current hypothesis versions with statuses/confidences,
`uncertainty.open_hypothesis_ids`, and `InterpretationRecord` handles per
interpretation. Selection policy itself is E2-D's design space; E2-C
guarantees every input it reads is fingerprinted, versioned, and
reproducible.

## Worked example

Baseline `turnover = 1.0`. One cost-shift test executes; observed
`turnover = 1.2` (rel +20%, clears the 1% band).

* H1 predicted INCREASE → SUPPORTS. PROPOSED@0.50 → UNRESOLVED@0.60.
* H2 predicted NO_CHANGE → CONTRADICTS. PROPOSED@0.50 → WEAKENED@0.40.
* H3 predicted DECREASE → CONTRADICTS. PROPOSED@0.50 → WEAKENED@0.40.

Three independent updates, one snapshot (`open: H-1, H-2, H-3`), zero
ranking. H1 is not "the winner" — it is merely the only rival whose
directional claim survived this test.
