---
name: agentic-evaluation-loop
description: Encode the EXPLORE-DIAGNOSE-REPAIR-VALIDATE stack (E0/E1/E2-A-F, selector key, directional-band v1, orchestration loop, repair pipeline, provisional v1 policy, budget invariants, determinism conventions). REQUIRED semantics kept distinct from implementation status. May consult S1 and S2.
---

# Agentic Evaluation Loop

May consult `milestone-integrity` (S1) for freeze/change protocol and
`indian-market-integrity` (S2) for environment execution rules. Owns no market
microstructure and no freeze registry.

## 1. Loop map (claim → file)

- **E0 contracts** (`evaluation/contracts/`): `TargetAgent` Protocol +
  `invoke_act` accepts ONLY `TargetObservation` (`agent.py`); oracle leakage
  boundary (`oracle.py`); `Hypothesis` separates observed `failure_class` from
  explanatory `mechanism` (must differ); lifecycle
  PROPOSED/SUPPORTED/WEAKENED/REJECTED/UNRESOLVED; `EvaluationBudget` immutable
  five-limit policy (`budget.py`); append-only `EvaluationState` with opaque
  `note_*` slots; SHA-256 canonical fingerprints (`fingerprints.py`).
- **E1 baseline** (`evaluation/baseline/`): trusted observation path
  (`trusted.py`); `run_baseline` is the sole execution authority client;
  25 metrics (`metrics.py`) where `None` means explicitly unmeasurable, never
  zero; one run consumes exactly 1 E0 episode.
- **E2-A contracts** (`diagnostics/contracts/`): ordering gates
  test → prediction → result → update; `budget_usage()` reports
  `{"tests": N}` only — do not extend it.
- **E2-B execution** (`diagnostics/execution/`): 5 closed intervention types;
  `COMPLETED` / `FAILED` / `INVALID` taxonomy; environment is execution
  authority; t−1 visibility (see S2).
- **E2-C interpretation** (`diagnostics/interpretation/`): directional-band v1,
  `TAU = 0.01`, confidence steps ±0.10, missed direction (incl. in-band) →
  `CONTRADICTS` by deliberate rule. Convention, not calibration.
- **E2-D selection** (`diagnostics/selection/`): key `(-D, -C, cost, test_id)`
  with D = rival-direction pairs, C = open-hypothesis coverage;
  state-conditioned, never optimality-claiming.
- **E2-E orchestration** (`diagnostics/orchestration/`): select → execute →
  interpret loop with iteration cap; scope must match baseline scope.
- **E2-F repair/validate** (`diagnostics/repair/`): proposal (provenance-bound)
  → copy-on-write application (original untouched) → three validation runs
  across two temporal windows (candidate@diagnostic, candidate@heldout,
  original@heldout; stored baseline is the diagnostic control, never rerun) →
  regression over all 25 metrics → provisional decision → `RepairResult`.

## 2. Budget semantics: REQUIRED vs STATUS

REQUIRED (invariant, versioned `e2f-budget-ledger/v1`): one admitted
`run_repair` = exactly 1 repair unit consumed BEFORE provider/application/
validation work; all outcomes (accepted/rejected/unresolved/provider,
application, validation failure) consume; one complete validation = exactly 3
validation-run units; `<3` remaining → validation does not start; partial
failure records invoked-run count N ∈ {1,2,3} with no rollback; accounting
persistent, deterministic, serialisable, fingerprintable, replayable.
STATUS: enforced by `RepairBudgetLedger` (`evaluation/diagnostics/repair/
accounting.py`), usage derived from persisted E0 note slots, never from
ephemeral counters. Historical note: at `d254cad` both budgets were
checked-but-not-consumed (`results.py` checked `{"repairs": 0}` /
`{"validation_runs": 0}` without recording usage) — never describe that
revision as satisfying these semantics.

## 3. Decision-policy caveats

`provisional-direction-dominance/v1` is an engineering rule, not calibrated
science. Return trade-offs are recorded, never adjudicated. Permanent
inactivity against a trading reference is REJECTED (inactivity guard), never
celebrated. `FAILED` (execution) ≠ `REJECTED` (scientific).

## 4. Determinism conventions

`freeze`/`thaw`, sorted-keys compact JSON, SHA-256 (`fingerprints.py`); every
contract round-trips `to_dict`/`from_dict` with unknown-field rejection; no
wall-clock, UUID, PID, randomness, or hidden counters in identity/accounting
paths; seeds are provenance-only. Per-package forbidden-token source scans
(e.g. `tests/diagnostics/repair/test_boundaries.py`) pin: no env/market
access, no oracle shortcuts, no learning/Bayes, no clock/randomness, no
`.adapt(` calls in repair paths. Extend token lists when adding code.

## 5. Test conventions

Cheap (hand-built frozen artefacts, in-memory) vs heavy (SMALL-window real
environment episodes) split by fixture; stub agents enforce
`TargetObservation`-only input; E0 provenance reads use `[-1]` append-order —
append admission/accounting entries BEFORE provenance notes, never after.

## 6. LEARN boundary and non-goals

LEARN is not implemented: no repair memory, no cross-agent policies, no
training loops. Explicit non-goals (frozen rationale: no calibrated basis):
Bayesian inference, LLM providers, multi-hypothesis repair, return-threshold
adjudication, repair search/optimisation.

## 7. Maintenance

Update claim→file references when milestones land; keep §2 REQUIRED list
intact and flip only the STATUS banner with the landing SHA.
