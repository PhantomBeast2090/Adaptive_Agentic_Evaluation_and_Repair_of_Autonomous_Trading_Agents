# Repair and Independent Validation (E2-F)

Status: repair + validation infrastructure (milestone E2-F). No learning,
no repair search, no Bayesian inference, no LLM.

Package: `evaluation/diagnostics/repair/`. Additive only; frozen
milestones, environment, data, and calendars untouched.

## Repair lifecycle

`RepairProposal` (immutable, fingerprinted, bound to an exact
target-agent fingerprint) → `apply_repair` (deep copy, wrap in
`GuardrailedAgent`, fingerprint both ends, original never mutated) →
`run_validation` (three E1 comparison runs) → `analyze_regression`
(explicit per-metric findings) → provisional decision → `RepairResult`
(ACCEPTED / REJECTED / UNRESOLVED / FAILED). Provenance anchors on the
diagnostic state's existing E0 note slots.

## Provenance

Every artefact carries method/version plus the fingerprints of its
inputs, forming an unbroken chain: diagnostic state → proposal →
application (pre/post) → candidate → validation runs → analysis →
decision. Artefacts travel by fingerprint; full objects are never
duplicated.

## Candidate isolation

Copy-on-write: the original agent object is fingerprinted before and
after (equal by construction — asserted by test), the copy is owned
exclusively by the wrapper, and failed applications discard the copy
while still recording an explicit FAILED application. Candidates expose
the `TargetAgent` surface without `adapt`, so they are non-adaptive
during validation.

## Validation independence

Validation reuses the frozen E1 runner, metrics, and environment
authority: candidate on the diagnostic window, candidate on a later
disjoint held-out window, original on the held-out window (same-window
comparison, no regime confounding). The stored original baseline
supplies the diagnostic-window control without rerunning recorded
history. The validator reports observations; the decision rule — not
the repair — judges them.

## Regression semantics

All 25 E1 metrics compared window-by-window as explicit deltas;
`None` stays `None`. Tolerance verdicts appear only for caller-supplied
named rules (default: none, no pass/fail asserted). Provisional v1
decision: UNRESOLVED on undefined targets; REJECTED on unimproved
targets, held-out regression, new zero-to-positive validity
violations, tripped tolerances, or total inactivity against a trading
reference; ACCEPTED otherwise. Return trade-offs are recorded, not
adjudicated — v1 has no calibrated basis for them, and the policy says
so explicitly.

## Leakage boundaries

The provider reads hypothesis claims, evidence references, and agent
policy snapshots — never market data, oracle packets, environment
state, or future bars. The repaired agent receives only
`TargetObservation` during validation. The held-out window starts
strictly after the diagnostic window ends, so reasoning evidence can
never leak into validation market conditions.

## Deterministic vs nondeterministic providers

`RepairProvider.deterministic` declares the contract. The v1 rule-table
provider is deterministic: identical inputs imply identical proposals
and, with a deterministic agent, an identical chain. A future provider
declaring `False` is supported structurally but excluded from
determinism claims by test.

## No-learning boundary

Nothing in E2-F persists across evaluations: no policy store, no
training loop, no memory, no optimisation. Each `run_repair` call starts
from its inputs and leaves only its returned artefacts plus E0 note
anchors. Reusable repair knowledge is an explicitly later stage.
