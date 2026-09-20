# E3-D Statistical & Experimental Protocol

**Milestone:** E3-D (protocol freeze; no runners, no experiments, no results).
**Status:** Tier 1 frozen pending review. Tier 2 gated — requires
replication/design amendment (see §11, §18).
**Normative rule:** this document freezes the meaning of "success",
"repair", "generalisation", "regression", and "efficiency" before any
experimental outcome is observed. After observation: no scientific
redefinition (§15).

---

## 1. Purpose and Scope

E3-D determines *how* the experimental campaign is conducted and
analysed — arms, units, replication, estimands, endpoints, guards,
missingness, reporting, and claim-clock rules. It creates no
runners, statistical code, benchmarks, windows, tests, or results.
Tier 1 (descriptive, exact, n=1, non-inferential) is executable after
this freeze. Tier 2 (confirmatory inference) is explicitly not.

## 2. Frozen Inputs

### 2.1 E3-A
RQ1–RQ5 (RQ5 future E4 only); F/A/N/R arm vocabulary; unit = one
complete agent×protocol×window execution; matched-comparison list;
held-out invisibility; return-insufficiency for RQ2; statistical
machinery deliberately deferred here.
### 2.2 E3-B
Benchmark classes; canonical `benchmarks/` home; move-not-duplicate
promotion; Class C deferred as missing dependency.
### 2.3 E3-C.2
Three canonical agents; frozen constants (VIX 15/25 convention,
uncalibrated); windows 2023-05-15→2023-06-15 / 2023-07-10→2023-08-10;
five-test pool; F-sequence with INVALID-non-fatal/FAILED-fatal
semantics; single-hypothesis Class-B (H-turnover only;
H-concentration rejected as intervention-created); manifest rev E3-C.2.
### 2.4 E0–E2
E1 25-metric inventory with `None` = undefined (never zero);
E2-D selector key and machinery unmodified; E2-E traces; E2-F
three-run validation geometry, ledger budgets (5/1/3),
`provisional-direction-dominance/v1` as an engineering rule (not a
significance criterion); fingerprint/canonicalisation machinery.

## 3. Experimental Unit and Reproduction

One complete agent×protocol×market-window execution = one
experimental unit, yielding one metric vector. Sessions are not units.
Trades are not units. Diagnostic tests inside one episode are not
independent replications. Repeated deterministic execution of the
same configuration is REPRODUCTION (verified by trajectory
fingerprint equality), not INDEPENDENT REPLICATION.

## 4. Experimental Architecture

Causal/evaluation chain: N → D → Repair → R → H, with D ∈ {D-F, D-A}.
F and A are diagnostic-policy variants, not separate repaired agents.

### 4.1 N — Original baseline
`run_baseline` of the original agent on the diagnostic window.
Reference for every contrast.
### 4.2 D-F — Fixed diagnosis
Diagnostic episode executing the pre-registered F sequence
(T-null, T-cost2x, T-uni-tcs, T-vintage-earliest, T-cost0) with
frozen stopping semantics. Never reselected post-hoc.
### 4.3 D-A — Adaptive diagnosis
Diagnostic episode through the frozen E2-D selector over the
identical pool, budget, environment, agent, hypotheses, and
information boundary. Only the selection policy differs from D-F.
### 4.4 Repair
E2-F repair bound to the diagnosed hypothesis (H-turnover for
Class-B), consuming 1 repair unit pre-work per the frozen ledger.
### 4.5 R — Repaired evaluation
Candidate on the diagnostic window (stored N baseline as control;
nothing already recorded is rerun).
### 4.6 H — Held-out evaluation
Candidate and original on the held-out window, same-window
comparison only.

## 5. Replication Policy

### 5.1 Current Tier-1 n=1
One window-pair; one execution per arm per window for any future
claim. Acceptable for descriptive/case-study-grade results only.
### 5.2 Reproduction
Each deterministic configuration may be repeated once, verified by
trajectory fingerprint equality, labelled REPRODUCTION CHECK. Never
counted toward n, never pooled as samples.
### 5.3 Future Tier-2 replication gate
Confirmatory inference requires genuinely distinct units:
additional non-overlapping window-pairs and/or independently
justified benchmark instances. Exact count is future work.
Gated: BLOCKED FOR CONFIRMATORY INFERENCE UNTIL REPLICATION
AMENDMENT (see §11, §18).

## 6. RQ1 — Diagnostic Capability

Resolution = terminal hypothesis state ≠ PROPOSED with committed
predictions, executed tests, interpreted updates, and a complete
E2-E trace linking every transition to its evidence fingerprint.
Provenance gaps disqualify the episode (INVALID per §13, not a
negative finding).

## 7. RQ2 — Repair Effectiveness

- **Estimand:** paired difference R − N in the primary endpoint on
  the diagnostic window, matched agent/config/seed (same agent,
  window, environment, configuration, costs, information policy,
  universe, execution semantics, seed provenance).
- **Primary endpoint:** Δturnover = turnover(R) − turnover(N),
  expected direction DECREASE. Turnover decrease alone is necessary,
  never sufficient.
- **Secondary descriptive endpoints:** order_count,
  executed_notional, transaction_cost_total, reversal_rate,
  inactivity_rate, validity metrics
  (invalid_order_count/universe_violation_count/no_price_count/
  calendar_gate_count and their rates), exposure metrics,
  risk/outcome metrics, and the complete 25-metric delta table.
  No composite score is constructed.
- **Mechanism correction** (the diagnosed mechanism changed as
  intended) is recorded separately from **collateral behavioural
  change**, **trading outcome change**, and **regression** (§13).
  A favourable return never overrides mechanism failure: return
  movement is reported under outcome change, never as repair
  evidence.

## 8. RQ3 — Held-Out Directional Persistence

- **Leakage boundary:** held-out data influences nothing diagnostic
  (hypothesis formation, test selection, repair, repair parameters,
  validation, stopping, repair memory, context). Diagnostic-window
  and held-out results are computed and reported separately; no
  observation contributes to both.
- **Estimands:** diagnostic-window improvement = R − N on the
  diagnostic window; held-out persistence = R − N on the held-out
  window (same-window candidate-vs-original in both cases).
- **Tier-1 criterion (directional persistence, not broad
  generalisation):** (1) primary endpoint defined on both arms of
  both windows; (2) held-out primary effect shares the
  pre-registered DECREASE direction of the diagnostic effect;
  (3) pre-registered regression guards do not trigger on either
  window; (4) no leakage/invalid execution occurred.
- If the diagnostic effect is undefined, held-out persistence is
  INCONCLUSIVE — no comparison is manufactured.
- n=1 never demonstrates broad statistical generalisation; the
  operational concept is directional persistence on unseen data.

## 9. RQ4 — Adaptive Diagnostic Efficiency

- **Limitation (frozen fact):** Class-B has one open hypothesis, so
  D(T) = 0 on every candidate. Pairwise hypothesis discrimination
  is structurally unavailable. No second hypothesis is
  manufactured; H-concentration stays rejected; no LLM is introduced
  to create competing hypotheses.
- **Current status: DESCRIPTIVE DIAGNOSTIC-POLICY SANITY COMPARISON
  ONLY.** Reportable per arm: tests consumed, terminal coverage,
  hypothesis resolution state, budget consumed, trace length,
  failure/invalid events, stopping reason, trace fingerprints.
  Behavioural F/A differences may be described; they must never be
  called evidence of superior hypothesis discrimination.
- **No scalar efficiency score is defined.** A future Tier-2 RQ4
  estimand requires ≥2 genuinely competing open hypotheses with
  D(T) ≥ 1 verified pre-execution on the frozen selector — i.e. a
  future scientifically justified benchmark/agent, explicitly
  specified at that time, never invented now.
- **RQ4 CONFIRMATORY DISCRIMINATION: BLOCKED UNTIL GENUINE
  MULTI-HYPOTHESIS BENCHMARK EXISTS.**

## 10. Tier-1 Statistical/Descriptive Analysis

Exact metric values; exact paired differences; direction checks
against pre-registered directions; operational guards (§14);
missingness incidence; full 25-metric tables; diagnostic traces;
budget consumption (ledger); fingerprints of every artefact.
No p-values. No confidence intervals. No confirmatory claims.
Language discipline: matched contrast, observed difference,
repair-associated change, diagnostic-window change, held-out
directional persistence. Causal verbs ("caused", "drove",
"improved" as a causal claim) are barred — Tier-1 supports
association under matching, never causal inference.

## 11. Tier-2 Inferential Analysis Gate

**NOT EXECUTABLE YET. GATED — REQUIRES REPLICATION/DESIGN
AMENDMENT.** Candidate inferential methods (provisionally specified
at design level only): paired permutation/exact test on
execution-level differences; Hodges–Lehmann paired shift;
execution-level bootstrap confidence intervals (unit = execution);
Holm fixed-sequence multiplicity (RQ2-primary-first). Final
specification — test, effect size, CI procedure, multiplicity,
resample counts, seed provenance — requires the replication
architecture first and is therefore not frozen here.
Mann–Whitney U remains excluded: the design is matched/paired, and
independent samples do not exist. Session-level tests, trade-level
tests, pseudo-replication, and deterministic repeats as samples are
barred in both tiers.

## 12. Metric and Missingness Policy

E1 vocabulary only; no replacement metrics. Per RQ: primary (§7–§9),
secondaries (§7 plus full delta tables), mechanism vs outcome
separation (§7). `None` means UNDEFINED/NOT MEASURABLE, never zero:
primary undefined on either arm → INCONCLUSIVE (never imputed as
zero/NaN/failure/success). Secondaries: report definedness,
missingness incidence with reason, and any exclusion explicitly —
never silent. `inactivity_rate` is a session fraction
(idle sessions with zero *submitted* orders ÷ total sessions);
undefined only when no decision records exist (degenerate episode).

## 13. Failure Taxonomy

Preserved E2 states, never conflated: natural behaviour /
controlled-benchmark behaviour / infrastructure-injected failure /
genuine experimental failure; INVALID intervention; FAILED
execution; hypothesis REJECTED vs UNRESOLVED; repair failure;
validation failure; regression (below); no-actionable-failure.
FAILED ≠ REJECTED; INVALID ≠ bad agent.

## 14. Pre-Registered Success Criteria

- **Tolerance:** REMOVED from Tier-1 criteria. Audit finding: the
  frozen substrate contains no pre-established tolerance —
  `ToleranceRule` is opt-in per-instance with no global default, and
  the campaign supplies none. No percentage or arbitrary numerical
  tolerance is introduced because no such threshold was
  pre-established in the frozen protocol. Exact/directional checks
  govern instead.
- **Inactivity collapse** (behavioural-collapse guard): reference =
  original agent N on the same diagnostic window. Collapsed iff
  inactivity_rate(R) == 1.0 while inactivity_rate(N) < 1.0
  (N demonstrated non-zero trading activity on the same scope).
  If N never traded (N == 1.0), the guard is vacuous, not failed.
  If either side is None, the guard is unevaluable → contributes
  INCONCLUSIVE, never success or failure.
- **Regression** (pre-registered, exhaustive): (A) validity —
  any validity count zero→positive on either window; (B)
  activity-collapse — §14 guard above; (C) mechanism — primary
  endpoint moves opposite the pre-registered direction;
  (D) outcome — secondary risk/performance deterioration, reported
  descriptively and flagged, but only (A)–(C) are hard failure
  criteria. All other secondary movement is descriptive, never
  auto-failure.
- **SUCCESS:** mechanism correction in the pre-registered direction
  + all mandatory guards pass + defined primaries.
  **INCONCLUSIVE:** primary undefined; insufficient resolution;
  budget exhaustion without resolution; unevaluable guards.
  **REGRESSION:** any hard guard in (A)–(C) violated.
  **INVALID:** leakage, overlapping windows, unfrozen
  configuration, invalid experimental identity, corrupted
  provenance. **FAILED:** execution/infrastructure failure.

## 15. Campaign Claim Clock

Frozen at E3-D commit: hypotheses, primary/secondary endpoints,
operational guards, regression definitions, Tier-1 criteria, RQ4
limitation, windows, arms, F-sequence, adaptive policy, pool,
budgets, missingness policy, reporting schema. After outcome
observation: NO SCIENTIFIC REDEFINITION. Any change = E3-D.x
amendment + explicit rationale + claim-clock restart. Temporal
windows are never silently extended.

## 16. Reporting Plan

Per RQ: endpoint table (value, sign check, guards, definedness);
paired-delta tables; trace/budget/fingerprint appendix;
None-incidence log; failure/invalid log. Trajectory figures only
as illustrations of reported numbers. Every table answers its RQ.

## 17. Scientific Limitations

n=1 per contrast (case-study grade; §5); single-hypothesis Class-B
(no RQ4 discrimination); deterministic substrate (no stochastic
generalisation claims); one window-pair (no regime-coverage claims);
Class C absent (no autonomy-validity claims); tolerance-free
criteria are exact by design, not by oversight.

## 18. Future Tier-2 Amendment Requirements

Replication architecture (additional window-pairs and/or instances,
exact n); final test/effect/CI/multiplicity freeze; resample counts
and seed provenance; re-freeze of any window-dependent bindings;
claim-clock restart record. Nothing here pre-executes Tier-2.

## 19. Decision Log

- Tier-1/Tier-2 split over single "ready": Tier-2 cannot be frozen
  without replication; pretending otherwise manufactures certainty.
- Tolerance removed, not invented: no frozen threshold exists;
  exact checks suffice at n=1.
- Inactivity reference = N on same window: only scientifically
  justified same-scope behavioural baseline available.
- No scalar efficiency: none defensible single-hypothesis.
- Mann–Whitney excluded: matched design, no independent samples.
- BuyOnce as control/reference only (§E3-C carries it; never an
  outcome benchmark, never a replication source).
- E3-C untouched: Tier-1 needs nothing it lacks.

## 20. E3-D Readiness State

**READY FOR TIER-1 PROTOCOL FREEZE / BLOCKED FOR TIER-2
CONFIRMATORY DESIGN.** Tier-1 is fully specified and executable
upon freeze. Tier-2 is gated on a replication/design amendment.
No Tier-1 ambiguity remains that is not grounded in frozen
substrate (tolerance and inactivity reference both resolved
above from actual frozen semantics).
