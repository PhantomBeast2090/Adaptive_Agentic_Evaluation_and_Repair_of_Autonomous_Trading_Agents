# Diagnostic Test Selection

This document describes the deterministic adaptive diagnostic test
selector (E2-D): what it optimises (nothing), what it guarantees, and how
to read its outputs. British English throughout.

## 1. Objective

Given the current diagnostic state after interpretation, determine the
next diagnostic test to propose — deterministically, auditably, and
without executing anything, inferring anything Bayesian, or ranking any
hypothesis.

## 2. Selector boundary

The selector reads `DiagnosticState` and writes one `SelectionRationale`
plus one `DiagnosticProposal` (or one `NoCandidateResult`). It never
touches the environment, market data, the executor, the interpreter,
repair, validation, or learning. It imports none of their modules
(enforced by source-scan tests).

## 3. Adaptive definition

Adaptivity here means state-conditioning: the preferred candidate is a
pure function of the *current* open-hypothesis set, committed
predictions, executed-test set, and budget state. As results and updates
change that state, discrimination counts recompute and the preferred
candidate can change. There is no fixed test order to replay; proving
this is the job of the adaptivity regression tests.

## 4. Candidate eligibility

A registered test is eligible only if it has no recorded result, the
budget is not exhausted, and at least one committed prediction ties it
to a currently open hypothesis. Every exclusion carries an explicit
reason (`EligibilityVerdict`); invalid candidates are never silent.

## 5. Open hypothesis definition

Open means lifecycle status PROPOSED, UNRESOLVED, or WEAKENED — reused
verbatim from E2-C (`OPEN_STATUSES`). SUPPORTED and REJECTED hypotheses
are closed for selection. No second definition exists.

## 6. Rival discrimination formula

For candidate T, D(T) counts unordered open-hypothesis pairs whose
committed predictions for T carry different `expected_direction`
values. Only the structured direction field is read; rationale prose
and magnitude text are never parsed. D(T) is an integer count, never a
probability.

## 7. Coverage

C(T) counts distinct open hypotheses with a committed prediction for T.
Hypothesis confidence values are readable state metadata but play no
role in coverage or ordering.

## 8. Cost

Each test's own frozen `estimated_cost`. Lower cost is preferred only
after discrimination and coverage tie. Costs are never measured,
estimated from data, or mutated.

## 9. Lexicographic selection

Key `(-D, -C, cost, test_id)`; the first candidate is preferred under
adaptive-discrimination v1. The `test_id` tie-break exists purely for
reproducibility.

## 10. Fallback policy

When no eligible candidate has D(T) > 0, the same key still decides and
every candidate description states that no directional rival separation
was available. No discrimination is fabricated. With no eligible
candidates at all, a frozen `NoCandidateResult` is returned instead of a
proposal.

## 11. Budget interaction

Budget is read via `budget_exhausted()` before any candidate work; a
zero or exhausted test budget yields `NoCandidateResult` suggesting
`BUDGET_EXHAUSTED`. Proposing consumes nothing — only E2-B execution
consumes test budget.

## 12. Stopping interaction

An already-set stopping reason yields `NoCandidateResult` echoing it;
the selector never sets, overwrites, or invents stopping reasons.
Suggested reasons for empty outcomes: budget-exhausted →
`BUDGET_EXHAUSTED`; open-but-untestable → `HYPOTHESIS_UNRESOLVED`;
nothing open → `NO_ACTIONABLE_FAILURE`. `SUCCESS_CONFIDENT` is never
suggested.

## 13. Proposal confidence

Structural selection-confidence, defined as 1.0 when the preferred
candidate separates at least one rival pair and covers every open
hypothesis under an eligible budget, otherwise
`coverage / total_open` clamped to [0, 1]. This is confidence in the
selection rationale — not hypothesis probability, posterior probability,
or belief in a mechanism.

## 14. Rationale structure

Every eligible candidate appears with its templated discrimination
sentence and cost; the preferred id; `selection_score` permanently
`None` (lexicographic choice computes no scalar score); method and
version stamps. Rationale and proposal ids derive from content
fingerprints, so unchanged state reproduces them byte-identically.

## 15. Determinism

Same state ⇒ byte-identical rationale, proposal, ordering, selection,
and ids. Any relevant state change (predictions, results, updates,
costs, budget) alters the affected identities. Verified by
determinism tests comparing independently built identical states.

## 16. Leakage boundary

Selection inputs are ids, directions, costs, statuses, and budget
counts. No observation, market, oracle, or chain-of-thought content
flows through the selector, and none is added to its outputs.

## 17. Why information gain is NOT claimed

The policy counts direction disagreements; it models no outcome
distribution, computes no entropy or divergence, and performs no
lookahead over hypothetical results. Calling D(T) "information gain"
would be a category error, so the codebase never does.

## 18. Why hypotheses are NOT ranked

Comparing tests by how they separate hypotheses says nothing about
which hypothesis is true — a test can cleanly separate two wrong
mechanisms. The artefacts contain no ordering, score, or probability
over hypotheses, and tests assert their absence.

## 19. Limitations

Single-step myopia (no multi-test planning); direction-only
discrimination (magnitude text unused); cost is static; proposal
confidence is structural, not calibrated; duplicate recording of an
unchanged selection correctly raises per frozen append-only semantics
(callers must check before re-proposing).

## 20. E2-E handoff

E2-E (closing the loop) consumes `DiagnosticProposal` +
`SelectionRationale` + `NoCandidateResult` as read-only inputs:
execute the preferred test via E2-B, interpret via E2-C, re-invoke
selection. Stopping suggestions inform — but do not dictate — the
loop's termination handling under the frozen E0 vocabulary.
