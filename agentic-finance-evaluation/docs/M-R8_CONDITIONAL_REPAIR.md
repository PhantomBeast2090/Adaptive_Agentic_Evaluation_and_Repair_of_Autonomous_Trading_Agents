# M-R8 — Mechanism-Specific Conditional External Repair: BOUNDED NULL

## Verdict

**NULL — CONDITIONAL-REPAIR-NULL: no admissible conditional repair under
fixed N1.** No held-out construction. No MemoryStore write. No
persistence/rollback. No replication. Per the pre-registered stop rule,
the programme terminates here; no further family, window, mechanism,
trigger, or threshold was introduced to seek a positive result.

## Design (strict isolation, frozen before adjudication)

Same NSE 6-name universe, same `MultiAssetChoice g1.yaml` (policy
fingerprint `db1a9a33…` preserved), same diagnostic window
`2020-01-01..2020-06-30` (123 sessions reused from the frozen M-R6
`base_diagnostic.json`, not rerun), same PIT-safe adapter, same
detectors (exposure support 46 selected), same 9 candidate
actions/params (byte-equivalent families/params asserted against M-R6;
compiled rule payloads cross-checked identical), same compile rules,
same economic/safety/statistical gates
(`seed 20260930, n_boot 5000, α 0.05`, tolerances `0.04/0.03`).

The ONLY change vs M-R6/M-R7 is the serving scope wrapper
(`evaluation/repair/conditional.py`, method
`conditional-exposure-scope/v1`):

```text
trigger TRUE  -> apply the byte-identical existing repair action
trigger FALSE -> reproduce the frozen baseline decision exactly
```

Trigger is EXACTLY the frozen exposure-mechanism condition
(`names_held > 2`, `max_normal_names=2`); no VIX, regime, price, future,
outcome, or additional predicate enters it (signature- and
behaviour-tested). Trigger/adjudication-flag parity asserted on every
adapted row. Trigger-inactive bit-equality proven by explicit tests
(conditional orders JSON-identical to baseline across all nine
families, not merely "no op invoked"); trigger-active byte-equivalence
against the broad `MemoryConditionedAgent` proven for the sampled
families.

Adjudication normality FIXED to N1 (mechanism-relative,
`d46b518f4c83ec01`), pre-registered in M-R7. N0/N2 reported as
descriptive sensitivity only; N2 survivors were NOT admitted.

## Adjudication (fixed N1, 0/9)

| Candidate family | N1 outcome | Reason |
|---|---|---|
| `exposure_cap{1}` | REJECT | bootstrap CI does not exclude null |
| `exposure_cap{2}` | REJECT | bootstrap CI does not exclude null |
| `max_quantity{4.0}` | REJECT | bootstrap CI + normal altered |
| `max_quantity{5.0}` | REJECT | bootstrap CI does not exclude null |
| `max_quantity{6.0}` | REJECT | bootstrap CI does not exclude null |
| `quantity_reduction{0.25}` | REJECT | normal-session behaviour altered |
| `quantity_reduction{0.5}` | REJECT | normal-session behaviour altered |
| `per_session_order_cap{1}` | REJECT | normal-session behaviour altered |
| `per_session_order_cap{2}` | REJECT | normal-session behaviour altered |

Sensitivity (descriptive): N0 0/9 NULL; N2 4/9 survive with
`per_session_order_cap{1}` ranked first — NOT admitted (N1 fixed; N2
protects only 6/123 sessions and was never the decision rule).

## What the NULL establishes

Conditional scoping moved the barrier downstream exactly as predicted:

- 4/9 candidates (both `exposure_cap`, `max_quantity{5.0}` and
  `max_quantity{6.0}`) now
  PASS normal-preservation under N1 — the M-R6/M-R7 spill onto
  mechanism-absent sessions is cured for these actions — but FAIL on
  bootstrap power (CI includes null). The repair is specific but the
  effect is not demonstrable under the frozen statistical gate.
  (`max_quantity{4.0}` fails both gates.)
- 4/9 candidates (both order caps, both quantity reductions) still FAIL
  normal-preservation despite single-step bit-equality on
  trigger-inactive decisions: altering trigger-active sessions changes
  subsequent portfolio state, so later mechanism-absent sessions diverge
  through path dependence. The intervention remains insufficiently
  specific at trajectory level.

The remaining barrier is therefore **trajectory-level intervention
specificity under portfolio-state path dependence**, compounded by
**bootstrap power** for the actions that are specific. No normality
redefinition, threshold movement, window change, or new family can be
justified within strict isolation.

## Negative controls (all refused/rejected)

- Opposite-side block (SELL): REFUSED at family eligibility.
- Unscoped `hold_all`: REFUSED at compile (UNCOMPILABLE).
- Total suppression (`order_cap 0`): REJECTED by the scope-aware
  inactivity guard (degenerate within-scope suppression; conditional
  serving cannot reach overall inactivity 1.0 by construction, so the
  frozen guard intent is enforced scope-aware; candidate adjudication
  untouched).

## Downstream (correctly unreached)

Freeze recorded the NULL (`freeze.json` with empty selection, trigger
`89aad28d…`, N1 fingerprint). Held-out NOT_CONSTRUCTED, no MemoryStore
writes, persistence/rollback NOT_ATTEMPTED, replication NOT_ATTEMPTED
(the 2020-H2 window was never read for decisions).

## Interpretation

M-R8 demonstrates that the observed natural-market NULL is robust to
the repair-language expressiveness change tested: even a
mechanism-gated, bit-faithful conditional intervention over the
identical candidate set admits nothing under the fixed N1 gate. The
programme therefore closes with a scientifically bounded NULL: external
memory/context repair is proven in controlled conditions (M-R4A/R1,
M-R5A–E) and proven to fail closed on the tested natural trajectory
across regime, mechanism-relative, hybrid, and now conditional serving
definitions. The architectural boundary discovered is trajectory-level
specificity under state path dependence, not trigger definability.

## Limitations

Single mechanism (exposure), single diagnostic window, single agent;
bootstrap CIs assume approximate stationarity; N2 sensitivity is
descriptive only; no weight-level claims.
