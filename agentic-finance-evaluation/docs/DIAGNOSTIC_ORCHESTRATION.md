# Diagnostic Orchestration

E2-E closes the diagnostic loop by orchestrating the frozen milestones:
E2-D selects, E2-B executes, E2-C interprets, and the controller repeats
the cycle against the updated state until an explicit terminal condition.
British English throughout.

## 1. Objective

Run a deterministic adaptive diagnostic loop over a supplied
`DiagnosticState`, returning a frozen `OrchestrationResult` that records
every iteration, the termination outcome, and the final state
fingerprint. The controller owns the loop and nothing else.

## 2. Architecture

`evaluation/diagnostics/orchestration/` holds five modules: `config.py`
(`OrchestrationConfig`), `controller.py` (`run()`), `results.py`
(`OrchestrationResult`), `trace.py` (`IterationTraceEntry`), and
`stopping.py` (the terminal-condition mapping table). All behaviour
lives in `run()`; the other modules are frozen data contracts plus one
lookup table.

## 3. State machine

`run()` validates inputs, then repeats while iterations remain: read
stopping state (defensive) → select → terminate on no-candidate →
execute → on failure record an uncompleted trace entry and continue →
on completion interpret and record a completed trace entry. The cap ends
the loop with `HYPOTHESIS_UNRESOLVED`. `DiagnosticState` is the single
authoritative state; the controller keeps no shadow copy, so every
selection and interpretation observes the actual updated state.

## 4. E2-D → E2-B → E2-C loop

Each iteration chains the three frozen calls with no logic in between
beyond trace assembly: `select_next_test(state)` yields a proposal or a
terminal outcome; `execute(...)` runs the preferred test and registers
its result; `interpret(...)` turns a completed result into updates and a
fresh uncertainty snapshot. Failed or invalid results skip
interpretation by construction, since `interpret()` admits completed
results only.

## 5. State ownership

All mutation flows through `DiagnosticState` public mechanics
(`record_rationale`, `record_proposal`, `record_result`,
`record_update`, `record_uncertainty`, `set_stopping_reason`). The
baseline artefact is read for control values and identity checks; it is
never duplicated into configuration nor mutated. Episode scope resolves
from the baseline config each iteration, with the loop seed offset by
the iteration index for distinct execution identities.

## 6. Budget semantics

Only E2-B consumes test budget, one unit per execution. The controller
checks exhaustion implicitly: an exhausted budget makes the selector
return a no-candidate outcome, which terminates the loop. Proposal
formation consumes nothing. `max_iterations` bounds loop passes and is
independent of the test budget; the two are asserted apart by test.

## 7. Failure semantics

`COMPLETED` results are interpreted; `FAILED` and `INVALID` results are
recorded visibly in the trace (`completed=False`, no interpretation
references) and the loop continues while budget, candidates, and the
iteration cap allow. Failures are never converted, never skipped
silently, and never interpreted as completed observations.

## 8. Determinism

Same initial state, baseline, configuration, agent, seed, and market
data produce byte-identical traces, identities, transitions,
termination, and final fingerprints — verified by double-run replay
tests. Identity derives from content fingerprints and the deterministic
`seed + iteration` episode scheme. No UUIDs, clocks, PIDs, randomness,
unordered iteration, or thread timing appear anywhere (source-scanned).

## 9. Trace structure

Each `IterationTraceEntry` carries iteration index, proposal, rationale,
test, result, episode, and execution references, plus interpretation and
update references when completed, bracketed by pre/post state
fingerprints. The final artefact adds the ordered trace, terminal
condition and stopping reason, any no-candidate reason, the final state
fingerprint, and method/version metadata. Artefacts live in state;
the trace holds immutable references.

## 10. Termination

Explicit conditions only: no-candidate outcome (with the selector's
suggested stopping echoed into state, defaulting to
`HYPOTHESIS_UNRESOLVED`), or the iteration cap
(`HYPOTHESIS_UNRESOLVED`). The stopping reason is set exactly once, at
exit. `SUCCESS_CONFIDENT` is never produced: ending a loop is not
evidence of diagnostic success.

## 11. Leakage boundary

The controller touches the state, the baseline artefact, and the agent
exclusively through frozen milestone calls; the agent itself is driven
only inside E2-B through `invoke_act`, receiving `TargetObservation`
alone. No market, environment, oracle, or observation-reconstruction
imports exist in this package (source-scanned).

## 12. Adaptivity definition

Adaptivity is state-conditioning across iterations: each selection,
execution scope, and interpretation reads the current state, so
evidence from iteration *i* reshapes iteration *i+1*. The regression
suite proves this causally — a rival-splitting first proposal, a real
execution and interpretation that moves hypotheses off their priors,
and a second proposal that differs because the state differs, never
from a hard-coded sequence.

## 13. Why E2-E does not perform repair

Diagnosis ends at termination: the artefact describes what was tested,
observed, and concluded. It carries no patch, no adapted agent, and no
validation verdict. `TargetAgent.adapt()` is never invoked (asserted by
test with a recording spy agent). Repair belongs to a later milestone
with its own contracts and safety analysis.

## 14. Limitations

Single-test-per-iteration loop (no batching or parallel episodes);
episode scope must equal the baseline scope: an explicitly supplied
window/universe is accepted only when it matches the baseline control
exactly (order-insensitive), otherwise the run is refused before any
selection or execution. Diagnostic interventions such as
`universe_restriction` remain explicit experimental factors inside the
matched episode scope; failed tests consume budget like completed ones;
iteration cap is a blind bound, not a convergence proof; trace
references require the live state or persisted artefacts to resolve
fully.

## 15. Future E2-F / repair handoff

E2-F consumes the terminal `OrchestrationResult` plus the final
`DiagnosticState`: supported/weakened hypotheses with their evidence
trails, open-hypothesis sets, and the full proposal→execution→
interpretation chain per iteration. Repair design must preserve the
frozen-state discipline established here — diagnose first, intervene
under separate contracts, validate independently.

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
