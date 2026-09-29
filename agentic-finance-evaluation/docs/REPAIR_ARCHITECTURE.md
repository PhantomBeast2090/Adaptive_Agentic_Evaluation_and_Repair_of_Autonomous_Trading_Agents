# Repair Architecture — External Memory-Conditioned Behavioural Repair (M-R0/M-R1)

## 1. Research motivation

The programme demonstrated evaluation, attribution, support construction,
diagnosis under support, and falsification — terminating in the I2 Class-C
NULL (no validated mechanism; see `docs/TERMINAL_RESEARCH_ASSESSMENT.md`).
The repair half of the thesis loop was architecturally ready but never
closed, for a precise reason: agents could *store* interventions
(`adapt()` appends) but no trading `act()` *consumed* them. This document
specifies the minimal additive architecture that makes retrieved external
memory causally effective while leaving every underlying policy bit-identical.

## 2. Internal adaptation vs external memory-conditioned repair

Internal model adaptation changes weights, gradients, or policy code; the
agent that acts after adaptation is a different function. External
memory-conditioned repair changes NOTHING inside the policy: the same
frozen function proposes orders, and a deterministic control plane —
driven by versioned, provenance-bearing memory entries — constrains the
proposal (truncate, breadth-cap, suppress) when scope and trigger
predicates match. The agent never "learns" internally; its behaviour is
externally memory-conditioned. The invariant is exact:

```text
policy fingerprint BEFORE == policy fingerprint AFTER
behaviour fingerprint BEFORE != behaviour fingerprint AFTER
```

proven by `base_policy_fingerprint()` (frozen snapshot machinery) and
twin-advanced untouched policies in `tests/repair/`.

## 3. Architecture

```text
FrozenTargetAgent (deep-copied, exclusively owned, never referenced)
        │ wrapped by
MemoryConditionedAgent (agents/wrappers/memory_conditioned.py)
  act(observation):
    base_orders   = base.act(observation)          # exactly once
    selection     = MemoryControlPlane.select(...)  # scope+trigger+conflict
    conditioned   = apply_rule_ops(base_orders, rules, observation)
    emit replay record (observation/base/result fingerprints, fired ids)
```

Evaluator side (offline): `FailureMechanism → RepairCompiler →
RepairSpec → MemoryEntry → shadow replay → verification gate →
admission (frozen extract→adjudicate→admit) → serving → held-out
verification → hash-chained audit`.

## 4. MemoryConditionedAgent

`agents/wrappers/memory_conditioned.py`. Owns a deepcopy of the base
(empty-store behaviour identical by construction); exposes `identity`
(base id + `+m{active-config-digest}`), `base_identity`,
`base_policy_fingerprint()`, `reset()` (delegates; store untouched),
`set_active()` (activation/rollback), `replay_log()` / `shadow_log()`,
`base_calls` audit counter. Construction is side-effect free
(`base.calls == 0` tested). Rule enforcement reuses
`GuardrailedAgent._apply_exposure_cap` plus identical hold_all/cap
semantics, pinned by a conformance test — a dedicated applier (not an
ephemeral GuardrailedAgent) is required because the base may be stateful
(re-invoking `act` would corrupt e.g. LossChasing loss counters).

## 5. ControlPlane (`evaluation/repair/control_plane.py`)

Retrieval: exact `agent_id` match over the serving list (serving list =
versioned materialization; MemoryStore stays system of record; every
served entry must reference an ADMITTED context via
`verify_admission`). Scope axes: agent/instruments/actions/vix-band/dates
(all must match; instrument-scoped entries never fire on unrelated or
empty orders). Triggers: ANDed `(field, op, value)` clauses over
vix/cash/exposure/order-sides/date; unusable fields fail closed.
Conflicts: specificity (scope axes + trigger count) > explicit priority >
version > sequence; full tie on differing rules → QUARANTINE (apply
neither). Lifecycle reuses `ContextStatus` for admission; deployment
state (shadow/active/deactivated) lives in the active set + audit chain.
Rollback = append-only deactivation; deactivated behaviour == base
behaviour (tested).

## 6. RepairCompiler (`evaluation/repair/compiler.py`)

Deterministic `FailureMechanism → RepairSpec | UNCOMPILABLE`, M-R1
vocabulary only (`per_session_order_cap`, `exposure_cap`, `hold_all`;
`max_quantity` reserved for M-R3 and rejected). Table: concentration /
exposure → breadth cap; volatility / regime / Execution → regime-triggered
`hold_all` (a missing vix trigger is UNCOMPILABLE — unscoped suppression
is unsafe); turnover / accumulation / risk / leverage / Risk/Sizing →
order cap. Unknown taxonomies → UNCOMPILABLE (stricter than the provider's
fallback default, deliberately: the compiler is the safe path).

## 7. Supported repair vocabulary

The three `GuardrailedAgent`-enforced types with their frozen
validators, plus the M-R3-authorised `max_quantity {cap}` (bounded size
truncation for escalation flaws; validator + enforcer +
provider-table row + compiler mapping; see `docs/M-R3_LOSS_CHASING_REPAIR.md`).

## 8. Lifecycle

`FailureMechanism → COMPILED → MemoryEntry → SHADOW → replay →
verification → admission (frozen gate) → ACTIVE → DEACTIVATED`
(rollback) — every transition a hash-chained audit event. No destructive
deletion anywhere.

## 9. Shadow mode

`shadow=True` returns base orders unchanged while recording what memory
would have done (`predicted_fingerprint` vs base). Unverified entries
never act; shadow/base divergence is itself a testable assertion.

## 10. Verification gate (`evaluation/repair/gate.py`)

Reuses the frozen triple + `_decide` policy untouched. Adds: deterministic
paired bootstrap CI and block bootstrap CI (seeded; evidence gates, never
proof), coverage precheck (unfired repairs unevaluable), and
`assemble_verification` composing everything into a `RepairVerification`
defaulting to NSF. Full gate (thresholds, held-out, tolerances) is wired
in M-R2; M-R1 establishes contracts + helpers.

## 11. Rollback

`deactivate()` returns a new active set; history preserved in caller +
audit chain. Tests prove deactivated behaviour == base behaviour and
policy twin-equality throughout.

## 12. Persistence

`MemoryStore.to_dict/from_dict` (frozen) + JSON entry/active-set
round trip, fingerprinted. Reloaded entries reproduce identical behaviour
(tested, including replay-log fingerprint equality). Process-memory-only
repair is insufficient by contract.

## 13. Provenance

`RepairAuditRecord` hash chain (`GENESIS` genesis, seq-linked,
tamper-evident: mutation breaks `verify()`), recording every lifecycle
transition with content fingerprints. Uses existing canonicalisation;
no second hashing system.

## 14. Policy fingerprint invariant

`base_policy_fingerprint()` (frozen snapshot machinery, adapter-aware via
`policy_snapshot()` through wrapper stacks) is asserted equal at
construction and twin-equal after any act sequence. The causal tests
prove memory moves ORDERS while policy-state evolution matches an
untouched twin exactly.

## 15. Frozen E0–I2 boundary

Zero frozen files modified (audit: `git diff` shows additive-only paths).
Thresholds, windows, permutation, miner, I2 Class-C NULL, YESBANK blocking
conditions all intact. Legacy `module_a/b/c/d` untouched and quarantined
by convention (MVP-only; never on the E0 path).

## 16. Why I2 remains NULL

Adequate support (56/32/22, 1743 TRAIN labels) met a frozen miner that
returned permutation parity plus confinement; the gate correctly refused
admission. The repair architecture here changes nothing about that
verdict — it builds the road the next validated mechanism would travel.

## 17. Controlled-benchmark path (M-R2/R3 executed)

R1 (`VolatilityBlindBenchmark` + `LegacyAgentAdapter`-independent
canonical E0 agent): regime-triggered `hold_all` → behavioural repair
demonstrated (31→2 / 6→2 high-VIX buys), gate REJECT on economics
(rebound forfeiture). R2 (`LossChasingBenchmark`): `max_quantity`
truncation → escalations 4→0 / 2→0, `_decide` ACCEPTED, gate NSF on
bootstrap power. Both labelled controlled/known-mechanism; no admission
occurred; see `docs/REPAIR_COMPLETION_REPORT.md`. Success claims remain
fenced to the benchmark, never natural discovery.

## 18. Explicit limitations

Single-act stateless selection (no cross-session memory state beyond base
buffers); trigger grammar is deliberately small; bootstrap CIs are
evidence gates under violated stationarity assumptions; the compiler
covers three rule types; calm-regime mechanisms outside gated scopes are
out of reach by design. No LLM, embeddings, vector search, or
self-editing anywhere in the canonical path.
