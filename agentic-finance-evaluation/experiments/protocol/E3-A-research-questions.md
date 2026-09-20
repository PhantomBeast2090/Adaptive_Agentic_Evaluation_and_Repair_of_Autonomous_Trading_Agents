# E3-A: Research Questions, Hypotheses, Variables, Estimands, Evidence Criteria

**Milestone:** E3-A (protocol only — no runner, no experiments, no results).
**Status:** protocol draft for review; no experimental claims are made here.
**Frozen infrastructure reused as-is:** Indian environment/data, E0 contracts,
E1 baseline (`evaluation/baseline/`), E2-A–E2-E diagnostics, E2-F
repair/validation with budget ledger (`e2f-budget-ledger/v1`).
**Normative rule for this document:** nothing here tunes protocol choices
against observed experimental outcomes; no result is presented as evidence.

---

## 1. Research questions

**RQ1 — Diagnostic capability.**
Can the adaptive evaluator identify actionable failure mechanisms in an
autonomous trading agent through hypothesis-driven diagnostic testing?

**RQ2 — Repair effectiveness.**
Does diagnosis-guided repair produce measurable improvement in the behaviour
associated with a diagnosed failure mechanism?

**RQ3 — Held-out generalisation.**
Do improvements produced through diagnosis-guided repair persist on a
previously unseen market period?

**RQ4 — Adaptive diagnostic efficiency.**
Under matched diagnostic budgets, how does adaptive diagnostic selection
differ from a fixed diagnostic strategy in its ability to discriminate
between competing failure hypotheses?

**RQ5 — Context learning. FUTURE E4 ONLY.**
Does validated context accumulated across evaluation cycles improve
subsequent agent robustness or diagnostic efficiency?
E3 must not represent RQ5 as an experimental claim. E3 preserves only the
provenance and interface awareness a future context-learning milestone
needs (§9).

---

## 2. Hypotheses

**H1 — Diagnostic resolution.**
The adaptive diagnostic process can transform competing hypotheses into
evidence-supported, weakened, rejected, or unresolved states through
executed diagnostic tests while maintaining complete provenance.
(Maps to E2-A lifecycle + E2-C updates + E2-E trace; RQ1.)

**H2 — Targeted repair.**
Diagnosis-guided repair produces a measurable change in the metric(s)
associated with the diagnosed failure mechanism relative to the
corresponding unrepaired agent. (RQ2.)

**H3 — Held-out generalisation.**
A diagnosis-guided repair that produces an improvement during the
permitted evaluation process produces a corresponding measurable
improvement on an independently held-out market period. (RQ3.)

**H4 — Adaptive efficiency.**
Under an identical diagnostic budget and candidate-test space, adaptive
test selection produces a different diagnostic efficiency/discrimination
profile from a fixed test sequence. (RQ4. Directional wording is
deliberate: superiority is not assumed pre-registration.)

**H5 — Context learning. FUTURE E4 ONLY.**
Validated context accumulated from prior evaluation cycles produces
measurable changes in subsequent diagnostic or trading-agent outcomes.
Not tested in E3; stated here only to fix the interface E3 must preserve.

---

## 3. Variable definitions

### 3.1 Independent variables

- **Diagnostic selection policy:** `fixed` (a pre-registered test sequence,
  see §11) vs `adaptive` (E2-D selector, key `(-D, -C, cost, test_id)`).
- **Repair condition:** `no-repair` (original agent) vs `diagnosis-guided-repair`
  (E2-F candidate bound to one diagnosed hypothesis).
- **Evaluation cycle:** `initial` (E3). `subsequent` is future E4 vocabulary;
  E3 records the cycle index in provenance but runs only initial cycles.
- **Agent type:** benchmark agent identity + version (exact set frozen in E3-B;
  see §11).
- **Market window:** predefined diagnostic and held-out date ranges (frozen in
  E3-B; see §7 and §11).

### 3.2 Controlled variables (pinned per experimental arm)

Environment version, dataset version (manifest SHAs), calendar version,
configured universe, transaction-cost model (`transaction_cost_bps`),
starting capital (`initial_cash`), information availability
(`strict_pit`, `vintage_policy`), execution semantics (t−1 visibility,
t-close fill, no carry-forward), diagnostic candidate pool, diagnostic
budget (`max_tests`), repair budget (`max_repairs`), validation budget
(`max_validation_runs`), agent version, seed provenance (provenance-only,
never consumed as randomness), protocol version (this document's revision).

### 3.3 Dependent variables (actual frozen E1 metric names)

Source of truth: `evaluation/baseline/metrics.py:635-661`
(`METRIC_FUNCTIONS`, 25 metrics, fixed order). Names below are verbatim;
semantics are the frozen implementations, not paraphrases. Any metric may
be `None` (explicitly undefined, e.g. dispersion over a single session) —
`None` is missingness, never zero.

**A. Mechanism-specific outcomes** (chosen per diagnosed failure mechanism
at E3-B registration; the mechanism↔metric binding is pre-registered, never
post-hoc):

- Turnover-type mechanisms: `turnover`, `order_count`, `executed_notional`,
  `transaction_cost_total`, `reversal_rate`.
- Exposure/concentration mechanisms: `gross_exposure_max`,
  `gross_exposure_mean`, `net_exposure_max`, `leverage_max`,
  `concentration_cost_basis_max`, `position_persistence`.
- Activity-collapse mechanisms: `inactivity_rate`.
- Validity mechanisms: `invalid_order_count`, `invalid_order_rate`,
  `universe_violation_count`, `no_price_count`, `calendar_gate_count`,
  `unavailable_info_session_count`, `unavailable_info_rate`.

**B. Trading outcomes** (recorded for every arm; never the sole evidence
for RQ2, see §6):

- `cumulative_return`, `volatility_per_session`, `sharpe_per_session`,
  `sortino_per_session`, `max_drawdown`, `worst_session_return`.

**C. Diagnostic outcomes** (from E2 artefacts, not E1 metrics):

- Hypothesis terminal-state distribution over
  {SUPPORTED, WEAKENED, REJECTED, UNRESOLVED} per diagnostic episode.
- Per-hypothesis update counts and compatibility sequences
  (SUPPORTS / CONTRADICTS / INCONCLUSIVE).
- Selector trace: tests proposed, ordered, and executed per iteration.
- Repair decision distribution over {ACCEPTED, REJECTED, UNRESOLVED, FAILED}.
- Budget consumption: tests/admissions/validation-runs used (ledger).

**Unmapped:** no E1 metric is currently unmappable — every metric sits in A
or B above. If a future mechanism needs an outcome outside this set, the
protocol must be amended (new metric = new milestone work), never
improvised per-experiment.

---

## 4. Experimental unit

The fundamental experimental unit is **one complete agent × protocol ×
market-window execution** — i.e. one full `run_baseline` trajectory (or one
full diagnostic/validation episode) yielding one vector of metrics.

Individual trades (orders, fills, sessions) must **not** be treated as
independent observations: they share the agent instance, the market path,
and temporal autocorrelation within the window. Any statistical treatment
that pools trades across sessions as i.i.d. samples is invalid for this
design; the unit of replication is the execution, and replication means
repeated executions under the replication structure frozen in E3-B.

**Matched comparisons:** the same agent identity/version, market window(s),
configuration, and seed provenance are evaluated under each arm
(fixed vs adaptive selection; no-repair vs repaired). Same-window
candidate-vs-original comparison (as E2-F validation already enforces)
removes regime confounding; cross-window comparisons are never used as
repair evidence.

---

## 5. Estimands (conceptual — no frozen formulae yet)

- **RQ2:** difference in the pre-registered mechanism-specific outcome
  (§3.3-A) between repaired and unrepaired conditions under matched
  experimental conditions (same agent, window, configuration, seed
  provenance).
- **RQ3:** difference between the repaired and the original agent on
  identical held-out data (same held-out window, same configuration).
- **RQ4:** difference in diagnostic selection/discrimination efficiency
  between adaptive and fixed selection under matched diagnostic budget and
  candidate-test space.

**Explicitly unresolved:** the exact numerator of "diagnostic efficiency"
cannot yet be justified from E2-D/E2-C semantics (candidate operational
choices include rival-pair discrimination rate per test, tests-to-first-
resolution, and update-sequence information — none selected). **No
statistical formula for diagnostic efficiency is frozen in E3-A, and no
statistical tests are selected here** (see §8).

---

## 6. Evidence criteria

- **RQ1:** traceable diagnostic resolution — hypotheses moved out of
  PROPOSED with committed predictions, executed tests, interpreted updates,
  and a complete E2-E trace linking every state transition to its evidence
  fingerprint. Provenance gaps disqualify the episode.
- **RQ2:** predefined mechanism-specific behavioural evidence (§3.3-A
  binding registered before execution). **`repaired return > unrepaired
  return` is NOT, by itself, sufficient evidence** that a diagnosed failure
  was repaired — return trade-offs are recorded, not adjudicated (E2-F
  provisional policy), and a return gain without movement in the
  mechanism-specific outcome is a non-finding for RQ2.
- **RQ3:** evidence computed on the held-out period that was inaccessible
  during adaptation (§7). Diagnostic-window improvement alone is never RQ3
  evidence.
- **RQ4:** measurable differences in selection/discrimination behaviour
  (selector traces, resolution profiles) under matched budget and
  candidate-test space — not assertional claims about adaptivity.
- **RQ5:** future E4 only; no E3 evidence criteria are defined.

---

## 7. Leakage and temporal integrity

The held-out period must not influence: hypothesis generation, diagnostic
test selection, repair selection, repair parameters, stopping decisions,
or future context updates. The protocol distinguishes **diagnostic /
evaluation data** (everything up to and including the diagnostic window
end) from **held-out validation data** (strictly later, non-overlapping —
the same separation E2-F `run_validation` enforces). Held-out windows,
once frozen in E3-B, are immutable for the experimental campaign; any
re-freeze restarts the campaign's claim clock.

---

## 8. Statistical design — preliminary only

No statistical test is selected in E3-A. The required decision chain,
to be discharged in E3-B or later before any confirmatory claim, is:

RQ → estimand → experimental unit → paired/unpaired structure →
distributional considerations → statistical test → effect size →
confidence interval → multiple-comparison treatment.

Final test selection occurs only after the E3-B benchmark/agent matrix,
temporal splits, replication structure, and experimental arms are frozen.
The Mann–Whitney U test (or any other named test) must **not** be
mechanically applied to every comparison: paired matched executions call
for paired treatment, `None` (undefined) metrics require a defined
missingness policy before any test, and per-session pooling is barred
by §4.

---

## 9. Context-update boundary (E4 concept, E3 preserves the interface)

Conceptual future architecture only — not implemented, not prototyped:

`ValidationResult` → `ContextUpdateCandidate` → eligibility checks →
`LearnedContext` (version + fingerprint + provenance).

Explicit rules E3 records for E4:

- **UNVALIDATED hypotheses must never become learned context.** Only
  ACCEPTED repairs with held-out generalisation are eligible inputs, and
  eligibility itself must be specified in E4.
- E3 artefacts already carry what E4 will need: fingerprints on every
  record, `RepairResult` decisions, validation reports, ledger entries —
  no additional E3 provenance work is required for this.
- No fake memory system is created in E3 to "satisfy" this section.

---

## 10. Traceability table

| RQ | Hypothesis | Independent variable | Dependent variable | Unit | Required evidence | Future arm | Dependency |
|---|---|---|---|---|---|---|---|
| RQ1 | H1 | selection policy | C: resolution distribution, traces | episode | §6-RQ1 provenance | E3 arms F/A | IMPLEMENTED NOW (E2) |
| RQ2 | H2 | repair condition | A: mechanism metrics; B recorded | execution | §6-RQ2 predefined binding | E3 arms N/R | IMPLEMENTED NOW (E2-F) |
| RQ3 | H3 | repair condition | A+B on held-out | held-out execution | §6-RQ3 held-out only | E3 arms N/R | IMPLEMENTED NOW (E2-F) |
| RQ4 | H4 | selection policy (matched budget/pool) | C: traces, resolution profiles | episode pair | §6-RQ4 matched differences | E3 arms F/A | PLANNED E3 (fixed-sequence fixture) |
| RQ5 | H5 (FUTURE) | evaluation cycle | TBD in E4 | TBD in E4 | none in E3 | FUTURE E4 | FUTURE E4 |

(Arms: F = fixed selection, A = adaptive selection, N = no-repair,
R = diagnosis-guided repair.)

---

## 11. Open scientific decisions (must NOT be frozen here)

- Exact benchmark agents (identities, versions, failure-mechanism coverage).
- Exact diagnostic and held-out temporal windows.
- Exact replication count and replication structure.
- Exact fixed diagnostic sequence for the F arm.
- Mechanism↔metric bindings per benchmark agent.
- Exact statistical tests, effect-size estimators, confidence procedures.
- Exact multiple-comparison procedure.
- Final diagnostic-efficiency formula (§5).
- `None`-metric missingness policy for statistical treatment.
- Campaign claim-clock / re-freeze rules beyond §7.

These are silently decided nowhere in this document; E3-B owns them.

---

## Scientific integrity audit (E3-A self-check, recorded)

- Every RQ measurable? RQ1–RQ4 yes via §6 criteria on existing artefacts;
  RQ5 explicitly deferred.
- Dependent variables available? Yes — all §3.3 names verified verbatim
  against `evaluation/baseline/metrics.py:635-661`; C-variables exist as
  E2/E2-F artefacts today.
- Circularity? H1 risks triviality (process completes ⇒ process capable);
  contained by requiring RQ4's matched contrast and RQ2/RQ3's behavioural
  evidence — resolution traces alone claim nothing about repair.
- Post-hoc success criteria? Barred: mechanism↔metric bindings and the
  fixed sequence must be pre-registered in E3-B.
- Temporal leakage? Barred by §7; held-out immutability enforced.
- Trades as independent samples? Barred by §4.
- Causal overclaim? Design supports matched-contrast causal language only
  within an arm pair (same agent/window/config/seed); cross-window or
  cross-agent causal claims are out of scope.
- Premature test selection? Barred by §8.
- Context/E3 separation? §9 + RQ5/H5 future-marking throughout.
