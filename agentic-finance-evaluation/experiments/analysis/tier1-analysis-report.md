# Tier-1 Analysis Report (Descriptive Only — No Inference)

**Status:** Tier-1 assembly + pre-specified descriptive analysis. No
p-values, CIs, effect-size inference, or multiplicity correction
executed (Tier-2 gated). Labels used: OBSERVATION / STATISTICAL
RESULT (none produced — stated where applicable) / INTERPRETATION
(withheld except pre-registered operational readings).
**Sources:** `results/e3/41e8f377…/feae2bf3….json` (T1-F, fixed),
`results/e3/8bae19f1…/a62865a3….json` (T1-A, adaptive). Integrity
run `8f439dc4…` excluded throughout.

## A. Integrity confirmation
Both artefacts reload with matching fingerprints (`ee175608…`,
`7c196279…`), TIER1_PRIMARY roles, unknown-field rejection intact.
Frozen substrate identical across campaigns except
`diagnostic_policy`. Independent lineages (4 distinct N/repair
fingerprints). Comparator bindings verified (seal == N-H,
repaired == R-H, aliases distinct). Leakage scan: held-out dates
only in configuration scope.

## B. Frozen protocol summary
E3-D Tier-1: exact paired differences, sign checks, operational
guards, missingness incidence, full tables, traces, budgets,
fingerprints. E3-D.1: Feb/Mar windows, single H-turnover
hypothesis, budgets 5/1/3, claim clock restarted.

## C. Analysis manifest
Consumed fields: 4 metric vectors + 2 delta maps per artefact;
diagnostic traces; lineage fingerprints; integrity/provenance
blocks. n=1 per contrast (2 campaigns = matched pilot pair, not a
replicated population). No imputation; E1 None semantics preserved
(None incidence: none — all 25 metrics defined on all four vectors
of both campaigns).

## D. RQ1 results
- OBSERVATION (T1-F): 5/5 fixed tests completed in manifest order,
  stopping `budget_exhausted`.
- OBSERVATION (T1-A): 2/2 tests (T-cost0, T-cost2x) via E2-D,
  stopping `no_candidate`.
- PROVENANCE GAP (recorded, not filled): terminal hypothesis states
  are not embedded in the persisted Tier-1 artefacts (trace carries
  completed tests, stopping, and state fingerprint only). The E3-D
  resolution bar (terminal state ≠ PROPOSED with complete trace)
  therefore cannot be fully verified from artefacts alone; trace
  completeness is verified, terminal-state verification requires
  the E2 diagnostic state, which was not persisted. No resolution
  claim is made here.

## E. RQ2 results
Primary endpoint Δturnover (R−N, diagnostic, DECREASE expected):
T1-F −0.5236, T1-A −0.5236 (identical — same deterministic
N-D/R-D pair recurs across campaigns; see §J).
Secondaries move with the mechanism (order_count −15/−15,
notional −52077.90, costs −26.04); validity counts unchanged at
zero on all vectors; inactivity unchanged (0.25 diag, 0.4286 held,
both arms — N traded, so the collapse guard is evaluable and does
not trigger). Return recorded only (diag +0.0241, held +0.0090),
never as repair evidence per frozen rule.

## F. RQ3 results
Held-out persistence criterion: same-sign held-out Δ + guards.
Δturnover held-out −0.4021 in both campaigns (same deterministic
held-out pair recurs). Guards pass (validity zero, no collapse).
Held-out isolation held (see leakage audit). Directional
persistence observed; broad generalisation not claimed (n=1).

## G. RQ4 results
T1-F: 5 tests, budget_exhausted. T1-A: 2 tests, no_candidate stop.
Status `DESCRIPTIVE_ONLY_SINGLE_HYPOTHESIS` both. No ranking, no
superiority language, no discrimination claim (D=0 frozen fact).

## H. Statistical analysis
Per E3-D §10–§11: descriptive statistics only. No inferential test
was authorised or executed for n=1; Tier-2 battery (paired
permutation, Hodges–Lehmann, execution bootstrap, Holm) remains
gated on replication. **STATISTICAL RESULT: none produced.**

## I. Missingness/undefined metrics
None incidence across all 8 vectors: zero. No exclusions, no
imputation paths exercised.

## J. Limitations
n=1 per contrast (case-study grade); determinism makes T1-F/T1-A
N and R pairs identical across policies, so the F/A contrast lives
entirely in the diagnostic traces, not the repair outcomes;
single-hypothesis Class-B (no RQ4 discrimination); one window-pair
(no regime coverage); Class C absent; tolerance-free exact
criteria by design.

## K. Claim boundary
OBSERVATIONS above are recordable. INTERPRETATION beyond
pre-registered operational readings (resolution met, directional
persistence observed with guards passing) is withheld pending the
authorised interpretive milestone. No causal verbs used. No
generalisation claim made.

## L. Reproducibility/provenance
Both campaigns reproducible from persisted configs + manifest +
supplement (deterministic identities verified pre-run); lineage
fingerprints in §A; E3-D hash `db846888…`, supplement filed under
E3-D.1; claim clock restarted at E3-D.1, no redefinition since
(git-verifiable).

### TABLE 1 — Substrate (identical except policy)
| Field | T1-F | T1-A |
|---|---|---|
| experiment_id | 41e8f377… | 8bae19f1… |
| policy | fixed | adaptive |
| benchmark | vol-threshold@1.0 | vol-threshold@1.0 |
| windows | Feb/Mar 2023 | Feb/Mar 2023 |
| universe/costs/cash/PIT | frozen identical | frozen identical |
| budgets | 5/1/3 | 5/1/3 |
| role | TIER1_PRIMARY | TIER1_PRIMARY |

### TABLE 2 — Diagnostic trajectories
| | T1-F | T1-A |
|---|---|---|
| tests | T-null, T-cost2x, T-uni-tcs, T-vintage-earliest, T-cost0 | T-cost0, T-cost2x |
| consumed | 5 | 2 |
| stopping | budget_exhausted | no_candidate |
| terminal hypothesis state | not persisted (see §D gap) | not persisted (see §D gap) |

### TABLE 3 — Repair-effect endpoints (turnover family + guards)
| metric | T1-F dD | T1-F dH | T1-A dD | T1-A dH |
|---|---|---|---|---|
| turnover | −0.5236 | −0.4021 | −0.5236 | −0.4021 |
| order_count | −15.0 | −12.0 | −15.0 | −12.0 |
| transaction_cost_total | −26.04 | −19.68 | −26.04 | −19.68 |
| validity counts Δ | 0 (all) | 0 (all) | 0 (all) | 0 (all) |
| inactivity Δ | 0.0 | 0.0 | 0.0 | 0.0 |

### TABLE 4 — Held-out generalisation endpoints
| check | T1-F | T1-A |
|---|---|---|
| held-out Δ sign | DECREASE (matches) | DECREASE (matches) |
| guards | pass | pass |
| isolation | held | held |
| status | directional persistence observed | directional persistence observed |

### TABLE 5 — RQ4 efficiency (descriptive, no ranking)
| | T1-F | T1-A |
|---|---|---|
| tests consumed | 5 | 2 |
| stopping | budget_exhausted | no_candidate |
| status | DESCRIPTIVE_ONLY_SINGLE_HYPOTHESIS | DESCRIPTIVE_ONLY_SINGLE_HYPOTHESIS |
