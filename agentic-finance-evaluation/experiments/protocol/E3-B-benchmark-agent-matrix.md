# E3-B: Benchmark and Agent Matrix

**Milestone:** E3-B (protocol/design documentation only).
**Status:** design artefact for review; no benchmark code, no experiments,
no results.
** arm vocabulary:** F/A/N/R exactly as established by E3-A
(F = fixed selection, A = adaptive selection, N = no-repair reference,
R = diagnosis-guided repair). No A0–A4 scheme is adopted.
**Normative rules:** E3-A is not modified to make E3-B easier; no temporal
windows, replication counts, statistical tests, or experimental results are
chosen here; threshold values for the Class B specification are E3-C work
and are deliberately absent.

---

## 1. Repository agent inventory (verified against source)

### 1.1 Legacy financial agents — NOT runnable benchmarks

`agents/financial_agent/` predates the Indian environment and the E0
`TargetAgent` contract:

- `synthetic.py`: `FlawlessControlAgent`, `LossChasingAgent`,
  `VolatilityBlindAgent`. Dict observations (`vix`, `market_price`,
  `portfolio` subkeys), single-asset BUY/SELL/HOLD dicts. No
  `AgentIdentity`, no `TargetObservation`, no order lists.
- `llm_agent.py`: `LLMTradingAgent`. Same legacy interface; `act()` is
  dummy deterministic logic behind a `# TODO` for a real LLM call.
- Six sibling `agents/*/` directories (adaptation, diagnosis, evaluation,
  orchestrator, repair, scenario, validation) are empty.

The loss-chasing and volatility-blindness behaviours in `synthetic.py`
are **designed benchmark behaviour in an unrunnable harness**: real as
descriptions, unusable as experimental targets. They inform future
Indian-compatible failure-benchmark design only and appear nowhere in
the matrices below.

### 1.2 Indian-compatible agents — test-local stubs only

The only agents implementing the E0 `TargetAgent` order-list contract
against `TargetObservation` live in test scaffolding:

- `tests/baseline/stubs.py`: `HoldAgent` (`hold-stub@0.1`, never trades),
  `BuyOnceAgent` (`buy-once-stub@0.1`, one scripted RELIANCE:EQ buy),
  `OutsideUniverseAgent`, `ChurnAgent`, `BrokenAgent`, `RecordingAgent`
  (with `TargetObservation`-only enforcement and explicit refusal to adapt
  legacy US agents).
- `tests/diagnostics/execution_fixtures.py`, `tests/diagnostics/fixtures.py`,
  `tests/diagnostics/repair/*`: mirrors plus `ExplodingAgent`,
  `TripleAgent`, `ChurnStub`/`HoldStub`, `GoldAgent`, observation spies.

`BrokenAgent`, `OutsideUniverseAgent`, and `ExplodingAgent` are
**diagnostic-validation infrastructure** (fail-closed and failure-injection
checks). They are permanently excluded from the research matrix (§9).

### 1.3 What does not exist

No trend-following, mean-reversion, or volatility-aware strategy agent in
Indian-compatible form. No runnable autonomous (LLM) agent. No statistical
utilities. No context-learning artefacts.

---

## 2. Benchmark classes

### Class A — Deterministic control agents

Scientific purpose: fully reproducible reference targets that validate
evaluator mechanics (episode execution, metric computation, trace
provenance, selector termination) independent of any trading hypothesis.
Sophistication is explicitly not required; predictability is the point.

- **A-hold `hold` lineage:** submits no orders on any session. Expected
  behaviour is known in advance (full inactivity, defined metrics where
  measurable, `None` where undefined).
- **A-buy-once `buy-once` lineage:** exactly one scripted opening trade, then
  holds. Exercises execution, fill, cost, and exposure paths with a
  minimal deterministic footprint.

Both are **candidates for promotion into canonical E3 benchmarks during
E3-C, not canonical benchmark implementations yet.** The test-local
`HoldAgent` (`hold-stub@0.1`) and `BuyOnceAgent` (`buy-once-stub@0.1`)
remain test scaffolding until E3-C establishes a single canonical
implementation under top-level `benchmarks/` with frozen benchmark
identities (e.g. `hold-benchmark@1.0`), at which point tests import and
reuse that implementation rather than duplicating benchmark logic.

### Class B — Static strategy agent (specified, not built)

Scientific purpose: a known trading policy, describable independently of
the evaluator, providing the core RQ2/RQ3 contrast (repaired vs
unrepaired) and the RQ4 discrimination substrate.

- **Single strategy for E3: volatility-aware threshold agent.**
  Reads India VIX (and only India VIX plus portfolio state) through
  `TargetObservation`; explicit deterministic rules of the form:
  below-threshold → build/maintain exposure within a fixed order cap;
  above-threshold → reduce exposure toward a fixed floor; otherwise hold.
  Stateless across sessions except a reset episode counter; no external
  state; no hidden information.
- **Threshold values, order sizes, and floor levels are E3-C decisions
  and are not tuned or chosen here.** Stating the rule shape without
  constants is deliberate: constants fixed before any evaluator run, in
  E3-C, pre-registered alongside the mechanism↔metric binding.
- Trend-following and mean-reversion families are explicitly deferred:
  one strategy suffices for the F/A × N/R contrasts, and each added
  strategy multiplies the arm matrix. Deferral rationale is recorded so
  a future extension is a scoped addition, not a redesign.

### Class C — Autonomous target agent (missing dependency, honestly stated)

Scientific purpose: the actual autonomous-trading-agent setting for which
adaptive evaluation and repair are intended. **No qualifying implementation
exists in the repository.** `LLMTradingAgent` does not qualify (legacy
interface, placeholder logic).

Minimum interface required of the future benchmark (E3-C or later, E4 at
latest for context work):

- Full E0 `TargetAgent` conformance through the `TargetObservation`
  boundary (§11).
- Provenance bundle: model identity/version, prompt and configuration
  fingerprint, tool configuration, environment fingerprint, agent
  package/version.
- Honest stochasticity statement per §8 (a seed is provenance, not a
  reproducibility guarantee, for LLM-backed decisions).
- No fake LLM/autonomous benchmark is created to fill this row; the
  C row of the participation matrix is marked deferred (§5).

---

## 3. Scientific role per benchmark agent

| Agent (canonical id in E3-C) | Class | Purpose | Policy | Inputs | Outputs | Determ.? | Stateful? | Ext. deps | Reproducibility | Repairable? | Validation-compatible? | Failure mode status | E3? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `hold-benchmark@1.0` | A | evaluator-mechanics control | never trade | TargetObservation | `[]` | yes | no | none | identical trajectories | no (nothing to repair) | yes (reference) | none expected; deviations are infrastructure bugs | yes |
| `buy-once-benchmark@1.0` | A | execution-path control | one scripted trade, then hold | TargetObservation | single-instrument orders | yes | episode counter, reset | none | identical trajectories | no | yes (reference) | none expected | yes |
| `volatility-threshold-benchmark@1.0` | B | strategy benchmark for RQ2/RQ3/RQ4 | VIX-threshold rules (constants in E3-C) | TargetObservation (VIX + portfolio) | capped orders | yes | episode counter, reset | none | identical trajectories | **yes** (core repair target) | yes | hypotheses to be tested, never assumed (§9) | yes |
| autonomous target | C | real-setting validity | vendor/model-defined | TargetObservation | order lists | stochastic (declared) | vendor-defined | model service, tools | provenance bundle, distribution-level comparison | yes, when available | yes, when available | hypotheses to be tested | **deferred** |

Repair compatibility means: fingerprintable by E2-F `fingerprint_agent`
(identity + policy snapshot), wrappable by copy-on-write application, and
runnable through three-run validation. All Class A/B agents satisfy this
by construction (deterministic, snapshottable `__dict__`); Class C must
demonstrate it before admission to the R arm.

---

## 4. Agent matrix (canonical)

| Agent | Class | Purpose | Deterministic? | Stateful? | External dependencies? | Repairable? | Required in E3? | Future? |
|---|---|---|---|---|---|---|---|---|
| hold lineage | A | control | yes | no | none | no | yes | — |
| buy-once lineage | A | control | yes | episode counter | none | no | yes | — |
| volatility-threshold | B | strategy benchmark | yes | episode counter | none | yes | yes | — |
| trend-following | B | strategy breadth | yes (if built) | tbd | none | yes | **no (deferred)** | possible extension |
| mean-reversion | B | strategy breadth | yes (if built) | tbd | none | yes | **no (deferred)** | possible extension |
| autonomous (LLM) target | C | real-setting validity | no (declared stochastic) | vendor-defined | model service + tools | when available | **no (deferred)** | E3-C or later; E4 context |

Repository terminology is used throughout (`AgentIdentity`,
`TargetObservation`, repair/validation per E2-F).

---

## 5. Experiment-participation matrix (F/A/N/R)

| Agent | F (fixed, no repair) | A (adaptive, no repair) | N (original reference) | R (repaired) |
|---|---|---|---|---|
| A hold | ✓ diagnostic-mechanics check | ✓ diagnostic-mechanics check | ✓ baseline reference | — (nothing to repair; cell deliberately empty) |
| A buy-once | ✓ | ✓ | ✓ | — (same reason) |
| B volatility-threshold | ✓ | ✓ | ✓ | ✓ (core RQ2/RQ3 contrast) |
| C autonomous | ✓ when available | ✓ when available | ✓ when available | ✓ when available (**deferred in E3**) |

Notes: A-row F/A cells test selector termination and trace provenance on
a null target — they support no discrimination claim. The B-row F/A/N/R
quadruple is the only full contrast in E3 and carries RQ2, RQ3, and RQ4
jointly. Empty R cells for Class A are meaningful (repairing a control is
scientifically vacuous), not omissions.

---

## 6. Agent identity, version, and fingerprint requirements

- Every benchmark agent carries an E0 `AgentIdentity` (`agent_id`,
  `version`) distinct from test-stub identities: benchmark ids live under
  `benchmarks/` (E3-C), test ids stay `*-stub@0.1` in tests. No id is
  shared across the two homes.
- Fingerprint = existing mechanisms only: `AgentIdentity.fingerprint()`
  plus E2-F `fingerprint_agent` (identity + policy snapshot) at
  proposal binding and candidate wrapping. No second identity system is
  created; if a future need exceeds these fields, the requirement is
  documented rather than redesigning E0.
- Versions freeze with the E3-C benchmark build; any rule/constant change
  thereafter is a new version, never a silent edit.

---

## 7. Reproducibility requirements

- Deterministic agents (all of E3): identical observation + configuration
  ⇒ identical action; `reset()` restores episode-local state and is
  asserted by test; identical inputs ⇒ identical trajectories, verified
  by fingerprint equality of repeated executions.
- Provenance recorded per execution: agent identity/version/fingerprint,
  configuration fingerprint, environment/dataset/calendar versions,
  universe, costs, capital, information policy, seed provenance, protocol
  revision (E3-A §3.2 controlled list).
- Stochastic agents (Class C, future): §8 policy applies.

---

## 8. Stochasticity policy

- "Same seed" is **not** equivalent behaviour for a deterministic agent
  (seeds are provenance-only; determinism comes from the policy and the
  frozen environment, and is proven by repeated-execution fingerprint
  equality, not by seed equality).
- For stochastic agents, provenance must include: seed(s), model
  identity/version, prompt and configuration fingerprints, tool
  configuration, environment fingerprint, agent package/version, and
  model parameters where applicable.
- An LLM run is **never** claimed perfectly reproducible from a seed.
  Documented limitation; strongest supported contract is provenance
  completeness plus distribution-level comparison across replications.
  Exact reproducibility, if ever demonstrated for a specific frozen
  model snapshot, must be proven by fingerprint equality — never assumed.

---

## 9. Failure-mechanism classification (anti-circularity)

Four distinct categories; every benchmark failure claim must carry one
of these labels:

1. **Naturally occurring behaviour** — observed in an agent whose rules
   were fixed for independent reasons (the Class B aspiration).
2. **Controlled benchmark behaviour** — rules fixed pre-registration that
   are expected to stress the evaluator (admissible for Class B).
3. **Deliberately injected failure for infrastructure tests** —
   `BrokenAgent`, `OutsideUniverseAgent`, `ExplodingAgent`. Confined to
   tests forever; never enters the research matrix.
4. **Actual experimental failure discovery** — hypotheses the evaluator
   forms and tests during E3 arms (the RQ1 claim).

Circularity guard: the benchmark population must not be built to
guarantee evaluator success ("create the failure, then find it").
Concretely: Class B constants are fixed in E3-C before any evaluator
run; the fixed F-arm sequence is pre-registered; mechanism↔metric
bindings are pre-registered (E3-A §6). The legacy `LossChasingAgent` /
`VolatilityBlindAgent` behaviours are category-2 descriptions in an
unrunnable harness — citable as design references, never as results.

---

## 10. Indian-market compatibility

Every E3 benchmark agent operates exclusively through the Indian
multi-asset environment interface: receives `TargetObservation` only;
orders well-formed Indian instruments within the configured universe;
assumes no US market structure, no foreign calendars, no synthetic price
feeds, no hidden macro variables. Strategy inputs (e.g. India VIX) are
observation fields actually present in `TargetObservation`, verified at
E3-C build time — never assumed from legacy dict keys.

---

## 11. Information-boundary verification

Benchmark agents must be verified unable to: access future bars or
future macro releases; access `EnvironmentState` directly; reconstruct
unavailable information (missingness is observed, never filled);
bypass the oracle boundary; read evaluator internals. Mechanism:
`TargetObservation`-only enforcement in `act()` (the established stub
`_require_observation` pattern becomes a benchmark requirement),
plus leakage-recording review of observation payloads at E3-C admission.
No existing agent was found violating this (stubs enforce it; legacy
agents cannot run at all). Any violation discovered later is documented,
never silently fixed in E0–E2.

---

## 12. Deferred agents and strategies

- Class B build (volatility-threshold constants, `benchmarks/` home):
  specified here, implemented in E3-C.
- Trend-following, mean-reversion: deferred with rationale (§2).
- Class C autonomous target: missing dependency; interface specified
  (§2); no placeholder built.
- Replication counts, temporal windows: E3-C/E3-D per E3-A §11.

---

## 13. Dependencies for E3-C onward

E3-C requires from E3-B: canonical `benchmarks/` home decision (taken:
new top-level package); promotion rule (taken: move-not-duplicate —
single canonical implementation, tests import/reuse it); Class B rule
shape (taken: VIX-threshold, stateless, capped); identity/version scheme
(taken: §6); boundary checklist (taken: §11). E3-C then freezes:
constants, identities, windows, replication, fixed sequence, bindings.

---

## 14. Explicit unresolved decisions

Whether the buy-once control adds resolving power beyond hold (E3-C may
drop A-buy-once with written rationale); exact Class B constants (E3-C, untuned);
whether Class C arrives in E3-C or later (dependency-gated, not
date-gated); trend/mean-reversion admission criteria for any future
extension.

---

## 15. Scientific-integrity audit (E3-B self-check, recorded)

- Population tests the RQs? RQ1 via A-row mechanics + B-row resolution;
  RQ2/RQ3 via the B-row N/R contrast on held-out data; RQ4 via the
  B-row F/A contrast under matched budget/pool. Yes.
- Meaningful control? Yes: Class A null targets separate evaluator
  mechanics from discrimination claims.
- Autonomous benchmark available? **No — honestly marked deferred**;
  E3 claims are accordingly scoped to strategy benchmarks.
- Fixed vs adaptive possible? Yes, pending pre-registered F sequence.
- Repaired vs unrepaired possible? Yes, via E2-F on Class B.
- Matched correctly? §7 matching list; same agent/version/window/config
  enforced; cross-window repair evidence barred (inherited from E3-A §4).
- Stochasticity honest? §8; no seed-equals-reproducibility claim
  anywhere, including for deterministic agents.
- Circular injection? Barred by §9 categories + pre-registration gates.
- Deferred dependencies clear? §12–§14.
