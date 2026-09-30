# Adaptive Repair Architecture (M-R5)

## Previous system vs new system

Previous: diagnosis → predefined repair → verification. One mechanism,
one hand-mapped repair (M-R4A: loss-chasing → max_quantity=5).

New: diagnosis → FailureMechanism model → candidate synthesis across
eligible families → shadow evaluation of every candidate → frozen
adjudication → selected repair frozen → held-out verification →
memory admission. The environment chooses among alternatives; no human
selects the winner; no thresholds move after results.

## Components

- **Mechanism detectors** (`evaluation/repair/adaptive.py`): pure
  functions mapping diagnostic traces to `MechanismSpec`
  (failure_type, trigger_context, affected_action, temporal_pattern,
  severity, frequency, support). Five types: loss_chasing, overtrading,
  exposure, volatility, drawdown. Each returns None below frozen
  support — abstention, not guessing.
- **Ontology** (`compiler.FAMILIES_FOR_TAXONOMY`): mechanism → eligible
  families. Restricts the search space before any evaluation.
- **Generator** (`generate_candidates`): frozen grids per family;
  max_quantity caps = three smallest distinct observed BUY quantities;
  block_action covers affected + opposite side (documented decoy);
  deterministic ids. Signature structurally excludes held-out data.
- **Compiler** (`compile_candidate`): family + params → RepairSpec or
  explicit Uncompilable (unknown family, ineligible family, invalid
  params, missing trigger). Existing `compile()` untouched.
- **Serving** (`MemoryConditionedAgent` + control plane): unchanged
  architecture; M-R5 adds four rule ops (quantity_reduction,
  cooldown_after_loss with wrapper-side arming windows, block_action,
  drawdown_risk_scaler) plus a `drawdown` trigger field resolved from
  own-portfolio accounting. Frozen `GuardrailedAgent` vocabulary
  untouched — new ops live on the serving path only.
- **Adjudicator** (`adjudicate_candidates`): must-pass gates (policy
  unchanged, fires>0, support, CI excludes null, normal-session
  preservation, validity, inactivity guard, economic tolerances) then
  ordering (largest target reduction, highest final value, lowest
  suppression, lexicographic id). P&L alone can never admit: the
  primary gate is mechanism-target reduction.
- **Experiment** (`scripts/run_adaptive_repair.py`): 18-step frozen
  pipeline; held-out constructed only after freeze.json exists
  (asserted); admission reuses provider → RepairResult → extract →
  adjudicate → admit; persistence + rollback proofs.

## Normal-session preservation (frozen rule)

Protected = base-compliant AND outside declared repair scope, where
scope = trigger match, plus armed suppression windows for cooldown
specs, and compliance-only for trigger-less specs. A session the repair
fires on outside this scope and alters is a violation → REJECT.

## What this establishes (and does not)

Establishes: the environment can construct several plausible external
repairs for a diagnosed mechanism, test them under frozen gates, reject
the unsafe/ineffective ones, select admissibly, and verify held-out —
all without touching the agent. Does not establish: natural-market
diagnosis (I2 Class-C NULL stands), universal repair efficacy, or
weight-level learning (no weights exist in this loop).

## Evidence separation (M-R6 terminal assessment)

### A. Controlled known-mechanism evidence: M-R4 / M-R5

Deterministic synthetic benchmarks with pre-registered flaws. M-R4A
admitted (loss-chasing, max_quantity); M-R5A–E demonstrated automatic
synthesis, adjudication, admission, persistence, rollback across five
mechanism families. These validate the repair *machinery*.

### B. Natural Indian-market evidence: M-R6

Real NSE trajectories, frozen MultiAssetChoice, outcome-blind
diagnosis. Result: NULL — exposure/overtrading detected with adequate
support, 9 candidates evaluated through the serving path, all refused
by the frozen gates (binding constraint: pre-registered
regime-relative normality vs mechanism-relative repair scope).
Machinery proven working on natural data; no mechanism admitted.

### C. Remaining limitations

- Normality is regime-relative by frozen definition; mechanism-relative
  normality remains an open design question (raised by M-R6, not
  resolved by it).
- Single canonical agent; single diagnostic/held-out pair.
- Bootstrap CIs assume approximate stationarity within windows.
- No weight-level or autonomous-policy claims anywhere in this system.
