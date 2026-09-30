# Adaptive Agentic Evaluation and Repair of Autonomous Trading Agents

**Manuscript draft — full paper with supplementary material.**
Language: British English. Claims are bounded to the evaluated protocols.

---

## Abstract

Static evaluation of autonomous agents reports behaviour under
predefined conditions but cannot search for conditional vulnerabilities,
explain them, or test whether targeted interventions generalise. We
present an adaptive agentic evaluation laboratory that closes this loop
for autonomous trading agents: baseline measurement, vulnerability
discovery, mechanism diagnosis, structured external repair synthesis,
verification, side-effect analysis, held-out validation, persistence,
and rollback — all without modifying the agent's internal model
parameters, architecture, or weights. Repair operates exclusively
through the external memory/context/control plane consumed by an
unchanged policy (`MemoryStore` admission served through
`MemoryConditionedAgent`, with policy fingerprints asserted invariant).

Evaluated on Indian-market data (NSE equities 2019–2026, NIFTY indices,
India VIX, USD/INR, RBI securities, MCX gold, CPI/IIP/policy events;
daily cadence, T-close execution, 5 bps costs, point-in-time-safe
information with vintage controls), the programme establishes: (i)
context can materially change behaviour without improving it (E4-E:
turnover 0.88→0.06, orders 30→2, no quality gain); (ii) controlled
external repair works (M-R4A `max_quantity=5.0` admitted, replicated
across four deterministic windows W1–W4 with 95% CIs below zero,
persistence and rollback demonstrated); (iii) adaptive repair synthesis
works in controlled conditions (M-R5: five mechanisms, eight families,
32 candidates, automatic selection with held-out isolation, negative
controls, 6–7 rejections per mechanism where warranted); (iv) the full
machinery ingests natural trajectories and fails closed (M-R6: 123
sessions, exposure support 46 selected, 9/9 candidates rejected under
frozen gates, no MemoryStore write); (v) the NULL is robust across
normality definitions (M-R7: N0/N1/N2 all 0/9 NULL); (vi) the NULL is
robust to mechanism-gated conditional serving (M-R8: identical nine
actions under trigger-scoped serving, fixed N1 adjudication, 0/9 NULL —
5 fail bootstrap power, 4 fail trajectory-level preservation through
portfolio-state path dependence).

The overarching natural-market repair claim is therefore NOT
established. The contribution is a validated external-repair boundary:
controlled adaptive external repair is demonstrated; natural-market
admissibility under the tested conditions is refuted for the candidate
set, with the binding constraint located in trajectory-level
intervention specificity rather than trigger definability. All
NULL/REJECT results are reported as first-class evidence.

---

## 1. Introduction

Evaluation of autonomous agents is dominated by static benchmarks: fixed
task sets, fixed scoring, single numbers. A capable agent may pass such
benchmarks while harbouring conditional vulnerabilities — behaviours
that are undesirable, measurable, and confined to identifiable
conditions (market regimes, portfolio states, behavioural histories).
Static evaluation cannot search for these; worse, evaluation and
improvement are usually separate processes, so even a discovered
weakness has no verified path to mitigation.

We study an integrated alternative: an agentic evaluation environment
that profiles the agent, searches for vulnerabilities in an
evidence-driven (not merely harder) manner, hypothesises mechanisms,
synthesises structured interventions, re-tests, checks side effects,
and validates generalisation on unseen conditions. The central design
decision — and the proposition this paper defends or bounds — is that
**repair need not modify the agent's internals**. The environment
diagnoses behavioural vulnerabilities and alters the external
memory/context/control conditions consumed by an unchanged policy; the
policy fingerprint is preserved while effective behaviour changes. This
distinguishes our work from fine-tuning, architecture search,
weight adaptation, and prompt-optimisation-as-training: the agent is
frozen, the world around it is repaired.

Trading is the experimental domain because historical market replay
provides rapid, measurable behavioural, risk, and economic feedback with
realistic microstructure constraints (point-in-time visibility,
corporate calendars, transaction costs). The architecture is intended to
generalise beyond trading; all empirical claims remain scoped to
autonomous trading agents on Indian-market data.

## 2. Related Work

**Autonomous agent evaluation** (AgentBench and successors) systematises
capability measurement but remains largely static: the environment does
not adapt to the agent under test. Our selector/diagnosis loop adds
agent-specific, evidence-driven adaptation with falsification gates.

**Financial benchmarks** (FinQA, FinanceBench, FinBen, ConvFinQA, TAT-QA)
test question-answering and reasoning over financial documents, not
sequential trading behaviour under market constraints; we use them as
data-provenance context, not as behavioural substrates.

**Trading agents and backtesting** provide the execution substrate
(portfolio accounting, costs, calendars) but optimise the trader; we
optimise the evaluator and hold the trader frozen.

**Safe/self-healing adaptive systems** study repair of software systems
through external controllers, an architectural precedent for our
memory/control-plane separation; we contribute its empirical validation
(and bounded refutation) for trading-agent behaviour with frozen
adjudication, persistence/rollback proofs, and held-out verification.

**Memory-augmented agents** typically treat memory as a capability
enhancement for the agent. We treat external memory as the *repair
surface of the environment*: admission-gated, fingerprint-verified,
rollback-capable, and causally effective only through serving.

Novelty is claimed precisely: not any component in isolation, but the
closed adaptive loop with external-memory repair, frozen falsification,
and demonstrated controlled efficacy alongside honestly reported
natural-market NULLs.

## 3. System Architecture

```
Trading Agent (frozen policy)
        v  observations (t-1 visibility only)
Adaptive Evaluation Environment (scenario selection, stress, observation)
        v
Evaluator (performance, risk, robustness, behaviour, consistency)
        v
Diagnosis (what failed / when / why / under what regime)
        v
Intervention synthesis (candidate repairs from eligible families)
        v  MemoryStore admission (gated) + control-plane serving
MemoryConditionedAgent (unchanged policy + served memory)
        v
Re-evaluation -> Regression/side-effect analysis -> Held-out validation
        v
Persistence proof -> Rollback proof -> Replication (where gated)
```

Components: mechanism detectors (pure functions over diagnostic traces,
abstaining below frozen support); repair ontology (mechanism → eligible
families); generator (frozen grids; `max_quantity` caps are the three
smallest distinct observed BUY quantities); compiler (family+params →
`RepairSpec` or explicit `Uncompilable`); serving
(`MemoryConditionedAgent` + control plane: scope filtering, trigger
evaluation, conflict resolution with quarantine on indistinguishable
conflicts, `GuardrailedAgent`-identical rule application); adjudicator
(must-pass gates then deterministic ordering); experiment runners
(frozen pipelines asserting held-out absence before freeze).

Normal-session preservation (frozen rule): protected = base-compliant
AND outside declared repair scope; any alteration of a protected
session rejects the candidate. M-R8 adds the conditional wrapper:
trigger-gated application of the byte-identical rule, baseline verbatim
otherwise.

## 4. Experimental Protocol

**Market:** NSE equities (~4,800 symbols, 2019-10-01→2026-09-11),
NIFTY 50/500, India VIX, USD/INR, RBI G-secs/T-bills, MCX gold (holiday
map absent → honest `NOOP_UNKNOWN_CALENDAR` blocks), CPI/IIP/RBI policy
events with explicit vintages. Brent excluded (NULL availability →
strict invisibility). Canonical 6-name NSE universe for M-R6/M-R7/M-R8
(`YESBANK, ICICIBANK, RELIANCE, SBIN, INFY, TCS` + `GOLDAUG2023`
placeholder); frozen `MultiAssetChoice g1.yaml` policy.

**Controls:** daily cadence, T-close execution, 5 bps costs, NOOP
taxonomy (`NOOP_UNKNOWN_CALENDAR/MARKET_CLOSED/NO_PRICE/UNKNOWN_ASSET`,
`NON_TRADEABLE_ASSET`, `INSTRUMENT_OUTSIDE_UNIVERSE`), PIT-safe t-1
information, vintage policies (`explicit/earliest/latest`,
unknown→`CONSTRAINT_FAIL`), venue-isolated calendars (UNKNOWN/CONFLICT
fail closed, no interpolation), configured-universe source of truth,
per-dataset SHA-256 manifests, deterministic replay with protocol/data/
policy fingerprints.

**Statistics:** paired bootstrap CIs (`seed 20260930, n_boot 5000,
α 0.05`), block bootstrap where dependence-aware, permutation tests for
representation claims, pre-registered support minima, tolerance bands
(value 0.04, drawdown 0.03), deterministic tie-breaks. Bootstrap bounds
are evidence gates, not proofs; non-stationarity is disclosed.

**Leakage controls:** retrospective legs (forward returns, MAE/MFE,
hold/opportunity counterfactuals, attribution outcomes, held-out
aggregates) refused by adapter construction and pinned by AST/signature
tests; generator/adjudicator signatures structurally exclude held-out;
freeze asserted before any held-out artefact exists; replication windows
never influence upstream decisions.

## 5. Controlled Experiments

**E0–I2 (frozen):** natural-market evaluation programme terminating in
I2 Class-C NULL — adequate support (56/32/22 contrasts; 2,458 labelled
rows), frozen miner, permutation parity, YESBANK candidate blocked by
experiment-level parity and single-instrument confinement. Correctly
unrepaired (untouched MemoryStore as protocol success).

**E4-E:** context→behaviour proven (turnover 0.88→0.06, orders 30→2,
validity clean) with NO quality improvement — contextual change is
causally effective but not sufficient for repair.

**E4-F/O:** accumulation untestable (systematic co-support, no separable
M2); outcome gaps ~95% non-participation, Sharpe undecidable.

**E5/M1:** deterministic attribution layer (`DecisionRecord`,
attribution engine, 42-row E5A set); historical replay traces absent
(0/0/0/0 arm counts) — not manufactured.

**M2–M4/P2:** representation NULLs (logistic Brier beaten by
permutation; HGB/sequence/Chronos/TimesFM miners 0 candidates or
blocked weights); timing benchmark NULL (formulation-level identity).

**M-R2/M-R3/M-R4B:** REJECT/NSF — reported, not rescued.

**M-R4A/R1:** admitted `max_quantity=5.0` (loss-chasing), replicated
W1–W4 with unchanged policy, persistence, rollback, CIs below zero —
core controlled evidence.

**M-R5A–E:** five mechanisms auto-diagnosed (supports 35/80/80/45/20),
32 candidates synthesised, mechanism-specific winners selected
(`max_quantity 5.0`, `order_cap 1`, `exposure_cap 2`, `hold_all`,
`cooldown 1` with deterministic tie-break), losers rejected (2–6 per
mechanism), held-out isolation, MemoryStore persistence, rollback,
negative controls. Corrections disclosed (cost-basis P&L fix, returns/
price-level fix, trigger-scoped normality).

## 6. Natural Experiments

**M-R6 (NULL):** 123 sessions (104 HOLD/9 BUY/7 SELL/3 MIXED);
exposure (46) and overtrading (18) detected, exposure selected by
support→severity→lexical rule; 9 candidates compiled, shadow-verified,
served; 0/9 survive (normal-preservation binding; breadth accumulation
concentrated in calm VIX sessions protected by the frozen regime rule).
No MemoryStore write, no held-out, no replication. Documentation-only
repo modification disclosed; CI non-reproduction disclosed.

**M-R7 (NULL×3):** N0 reproduces M-R6 exactly (conflict 0.870); N1/N2
remove conflict (0.000) yet still 0/9 NULL — binding constraint shifts
to intervention specificity (repairs leak onto mechanism-absent
sessions) plus bootstrap power. NULL robust across normality
definitions; impossibility not claimed.

**M-R8 (NULL, this work):** strict-isolation conditional serving;
trigger exactly `names_held > 2`; nine actions byte-equivalent; fixed
N1 adjudication. 0/9 NULL: 5 fail bootstrap power only (both
`exposure_cap`, all three `max_quantity` now preserve normality but
show no demonstrable effect), 4 fail trajectory preservation only
(order caps, quantity reductions — single-step bit-equality holds, but
portfolio-state path dependence propagates alterations into later
mechanism-absent sessions). N2 sensitivity (4/9 survive, order-cap-1
first) descriptive only, not admitted. Programme terminates per stop
rule.

## 7. Ablations

Removing adaptive selection reduces the system to static benchmarking
(no vulnerability search); removing diagnosis reduces synthesis to
predefined repairs (M-R4A baseline); removing conditional scoping
reverts M-R8 to M-R6 broad serving (normal-preservation failures return
for 5/9); removing the statistical gate would admit bootstrap-null
effects (5/9 under M-R8-N1); removing held-out isolation would permit
selection on validation outcomes (structurally excluded). Each
component's contribution is thus isolated by a frozen comparison.

## 8. Statistical Analysis

Deterministic synthetic evidence (M-R4A/R1, M-R5) carries no sampling
uncertainty beyond the reported bootstrap CIs; generalisation claims
are explicitly disavowed there. Natural-market evidence rests on 123
diagnostic sessions with block-aggregated paired differences; CIs assume
approximate within-window stationarity (disclosed limitation).
Permutation testing falsified representation claims (M1/M2/I2).
Support counts gate every detection and adjudication decision
(`min_support` 10/6). The M-R8 outcome pattern (specificity without
power vs power without specificity) is reported as observed, not as a
calibrated trade-off curve.

## 9. External Memory Repair

Internal modification (weights, architecture, gradients, hidden policy
state) never occurs: base policies are deep-copied, fingerprinted
before/after every decision, and asserted equal in every trace,
persistence, and rollback proof. All behavioural change flows through
admitted `MemoryEntry` records served by the control plane. The
dedicated contribution is this separation made auditable: admission
provenance, serving selection records, replay logs, shadow predictions,
persistence round-trips, and rollback restorations are all
deterministic, serialised, and fingerprinted.

## 10. Persistence and Rollback

Demonstrated wherever admission occurred (M-R4A, M-R5A–E): reloaded
store+entry fingerprints match, re-served behaviour reproduces exactly,
deactivation restores baseline bit-identically, policy fingerprints
invariant throughout. Correctly unattempted on all NULL paths
(M-R6/M-R7/M-R8): no store files exist there by assertion-checked
construction.

## 11. Failure and NULL Results

E4-F, E4-O, M1, M2, M4, P2, M-R2, M-R3, M-R4B, I2, M-R6, M-R7, M-R8 are
reported with mechanisms, counts, and binding constraints. They
constitute the paper's second result: a mapped boundary of where
external repair does not currently work and why.

## 12. Limitations

Single canonical agent/policy; single diagnostic/held-out pair per
natural experiment; single mechanism reaching M-R8 adjudication;
stationarity assumptions in bootstrap CIs; calm-regime-only mechanisms
untested; E2-F lineage scope (evaluation-loop contracts) out of scope
for trading claims; runtime (not CI-reproduced) test evidence for the
full suite; ~1 GB NSE re-parse cost per episode constraining full-suite
frequency; no weight-level, profitability, optimality, or universal
repair claims.

## 13. Conclusion

Under the evaluated protocols, an external evaluation environment can
diagnose behavioural vulnerabilities and repair effective behaviour
without touching the agent — in controlled conditions automatically
(M-R5), with replication (M-R4A-R1). On the tested natural Indian-market
trajectory, the same machinery diagnoses, synthesises, verifies, and
fails closed across four serving/normality definitions (M-R6/M-R7/M-R8),
establishing a bounded NULL whose mechanism is trajectory-level
intervention specificity under portfolio-state path dependence. The
answer to the research question is therefore PARTIAL with a precise
boundary: YES in controlled known-mechanism conditions; NOT ESTABLISHED
— and specifically refuted for the tested candidate set — on the
natural trajectory studied.

---

## Supplementary Material

**S1. Protocols:** `configs/adaptive_repair/{mr5a-e,mr6_natural,
mr7_normality,mr8_conditional}.yaml` with fingerprints
(M-R8 protocol `8ebbe7ec…`, trigger `89aad28d…`, N1 `d46b518f…`).

**S2. Artefacts:** `data/adaptive_repair/{M-R5A-E,M-R6,M-R7,M-R8}/`
(manifests, adjudications, candidate results, audits, normality
matrices, conflict analyses, freeze records; held-out/store/
replication present only where admitted).

**S3. Reproduction:** `scripts/run_{mr6,mr6_controls,mr7,mr7_controls,
mr8,mr8_controls}.py --base-dir .` (M-R8 refuses overwrite without
`--overwrite`); `pytest tests/repair/ tests/diagnostics/repair/
test_budget_accounting.py` (130 passed at M-R8 commit).

**S4. Data contracts:** `INDIAN_DATA_CONTRACT.md`,
`INDIAN_DATA_SOURCE_INVENTORY.md`, manifests under
`data/manifests/india/`; execution semantics in §4.

**S5. Configuration descriptions:** agent
`configs/choice_agent/g1.yaml`; environment
`configs/indian_environment.yaml`; detection/adjudication grids in S1.

**S6. Statistical outputs:** per-candidate `target_reduction`,
`ci_lower/upper`, `fires`, `suppression_rate`, `final_value`,
`drawdown`, `inactivity` in each `candidate_results.json`; bootstrap
parameters frozen in protocols.
