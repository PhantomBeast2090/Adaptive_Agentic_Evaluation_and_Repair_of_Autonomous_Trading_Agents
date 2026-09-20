# E3-C: Canonical Benchmarks and Experimental Temporal Protocol

**Milestone:** E3-C (frozen substrate + protocol; no substantive experiments).
**Status:** frozen pending review; zero experimental-result language by design.
**Revision:** E3-C.2 (supersedes E3-C.1: H-concentration removed per
narrow scientific audit; see §6. Class-B is single-hypothesis.)
**Manifest:** `benchmarks/manifest.yaml`, protocol revision E3-C.2,
sha256 `412deb50682d5bea5a8283278764e4e416547d09b4cf04d93141e76f230dca86`.

---

## 1. Scope

E3-C converts the E3-B design into runnable, fingerprinted substrate:
three canonical benchmark agents, frozen constants, frozen temporal
split, frozen mechanism↔metric bindings, frozen candidate pool, frozen
F-arm sequence, frozen replication structure. Out of scope: experiment
runner, statistical pipeline, substantive experiments, Class C
autonomous agent, trend/mean-reversion agents.

## 2. Temporal ownership correction

E3-A §11 assigned window ownership to E3-B; E3-B deferred windows to
E3-C/E3-D. No frozen window existed before this document. **E3-C hereby
claims ownership and freezes the temporal split below.** E3-A's wording
is superseded by this protocol ownership statement; E3-A itself is
unedited (no historical rewriting).

## 3. Frozen temporal windows (Candidate 1, outcome-independent)

- Diagnostic: 2023-05-15 → 2023-06-15 (24 NSE_CM OPEN/SPECIAL sessions,
  0 UNKNOWN, 8 CLOSED weekend/holiday sessions).
- Held-out: 2023-07-10 → 2023-08-10 (24 OPEN/SPECIAL, 0 UNKNOWN).
- Strictly later, non-overlapping; no embargo period (adjacent-regime
  gap is inherent in the 25-day separation).
- Selection basis only: chronological order, dataset coverage overlap
  (`2019-10-01..2026-09-11`), fully-covered calendar year (2023,
  VERIFIED; 2024 excluded for partial circular coverage), ≥20 sessions
  per window, test-alignment with the SMALL config family, gold-contract
  continuity. No returns, no diagnostic success, no performance
  inspected at any point in selection.

## 4. Constants register (design conventions, explicitly uncalibrated)

VIX thresholds 15.0/25.0: pre-existing repository convention (legacy
control rules, scenario configuration). Recorded as convention, never
as calibration. Boundary equality → MID/HOLD tie rule. Missing VIX →
hold (no imputation, no forward fill). Build quantity 1.0 per name,
reduce quantity 5.0 per held name toward floor 0, cash dust 1.0,
max 3 orders/session, cash 100000.0, costs 5.0bps, strict PIT,
explicit vintage. Frozen universe: NSE {RELIANCE:EQ, TCS:EQ}, MCX
{GOLDAUG2023}. None fitted, estimated, or tuned.

## 5. Benchmark specifications

- `hold-benchmark@1.0` (`benchmarks/hold.py`): `[]` on every valid
  observation. Mechanics/provenance control. Not repairable.
- `buy-once-benchmark@1.0` (`benchmarks/buy_once.py`): one BUY
  RELIANCE:EQ q=10 at first eligible decision; holds after; counter
  reset. Execution-path control. Not repairable.
- `volatility-threshold-benchmark@1.0`
  (`benchmarks/volatility_threshold.py`): LOW → one BUY per
  configured NSE name (diversified accumulation is the strategy;
  multi-order output is its consequence, never a repair-driven
  choice); MID → hold; HIGH → SELL held names up to 5 toward floor 0;
  missing VIX → hold. Deterministic; reset restores the episode
  counter; no `adapt` surface (repair stays copy-on-write).

**Independence statement (Amendment 1):** the benchmark is specified
independently of the repair provider. No benchmark code imports,
calls, names, or encodes knowledge of E2-F provider rules
(`rule-table`, order caps, TripleAgent mechanics, or any equivalent).
Any compatibility between an emergent mechanism and an available repair
rule is an experimental property, not a benchmark construction
requirement. Had no defensible mapping emerged, the incompatibility
would have been recorded instead — the mapping below survived that
test, it did not drive construction.

## 6. Hypothesis analysis: single-hypothesis benchmark (E3-C.2)

Class-B carries exactly one scientifically defensible hypothesis:

- **H-turnover** (`failure_class="turnover"`): rule-based accumulation
  across two names sustains elevated order flow in low-volatility
  regimes.

It uses the frozen E0 Hypothesis contract with distinct
failure_class/mechanism. No second hypothesis is manufactured, and none
is needed for the benchmark to function.

### Rejected hypothesis (audit record, not history rewriting)

E3-C.1 additionally carried **H-concentration**
(`failure_class="concentration"`, mechanism "persistent accumulation
concentrates cost basis in the traded names", primary metric
`concentration_cost_basis_max` INCREASE). The E3-C narrow scientific
audit rejected it:

- Baseline Class-B behaviour accumulates equal quantities in two names;
  its cost-basis structure is diversified by construction (≈0.5 on
  `concentration_cost_basis_max`, the structural minimum for a
  two-position book). No baseline concentration failure exists.
- The pre-registered prediction (T-uni-tcs →
  `concentration_cost_basis_max` INCREASE, 0.5→1.0) is a mathematical
  consequence of restricting the universe to one instrument, not
  discrimination of a baseline mechanism.
- H-concentration therefore served as manufactured discrimination
  (a metric that moves under intervention, kept to make D(T)=1).

H-concentration is removed from the active protocol. This section
preserves the rejection and its reason so the history stays legible.

### Discrimination consequence

With one open hypothesis, D(T) = 0 for every candidate test while C(T)
continues to reflect single-hypothesis coverage. The frozen E2-D
selector is unchanged and still returns deterministic candidates
(ordered by coverage, cost, test id). The protocol distinguishes three
things that must not be conflated: **selector operation** (functions
normally), **hypothesis-pair discrimination** (structurally unavailable
for Class-B — correctly so), and **adaptive evaluation generally**
(untouched as a research programme). Class-B therefore demonstrates no
pairwise discrimination, and no such claim is made. Strong RQ4
discrimination evidence is deferred to E3-D experiments containing
genuinely competing hypotheses; RQ4 itself is untouched (E3-A unedited).

## 7. Mechanism ↔ metric mapping (pre-registered)

| Hypothesis | Primary metric (direction) | Secondary metrics | Diagnostic evidence required | Provider mapping (pre-registered, not driving) |
|---|---|---|---|---|
| H-turnover | `turnover` DECREASE | `order_count`, `transaction_cost_total` | committed prediction + executed test + interpreted update | `rule-table/v1` turnover row → order cap, target turnover/DECREASE |

All metrics from the frozen E1 25-inventory; none invented.
`cumulative_return` is recorded, never sole repair evidence (E3-A §6).
T-uni-tcs remains in the pool as a legitimate H-turnover diagnostic
(fewer names to accumulate → less order flow); its concentration
reading is descriptive arithmetic, not hypothesis evidence, and is
never used as such.

## 8. Candidate diagnostic pool

T-null (`null_intervention`), T-cost2x (`transaction_cost_shift ×2.0`),
T-cost0 (`transaction_cost_set 0.0`), T-vintage-earliest
(`vintage_policy_shift earliest_available`), T-uni-tcs
(`universe_restriction` to TCS:EQ) — all existing E2-B types, cost 1.0
each. No new intervention invented.

## 9. Prediction matrix (pre-registered directions, H-turnover only)

| Test | H-turnover predicts |
|---|---|
| T-null | turnover NO_CHANGE (control) |
| T-cost2x | transaction_cost_total INCREASE |
| T-cost0 | transaction_cost_total DECREASE |
| T-vintage-earliest | turnover NO_CHANGE |
| T-uni-tcs | turnover DECREASE (fewer names → less order flow) |

Magnitudes are never pre-registered (directional-band interpretation is
relative-change based); only directions are frozen. No concentration
prediction appears: the removed H-concentration row is documented in
§6, not silently dropped.

## 10. F-arm sequence and stopping semantics (Amendment 3)

Frozen order: `[T-null, T-cost2x, T-uni-tcs, T-vintage-earliest,
T-cost0]`. Execution semantics: COMPLETED → continue; INVALID →
record and continue (non-fatal); FAILED → record and halt (fatal);
budget exhausted → halt; sequence exhaustion → finish. These semantics
are data in the manifest, not runner code (no runner is built in E3-C).

## 11. Adaptive-arm relationship

The adaptive arm uses the identical candidate pool through the frozen
E2-D selector (unmodified). Pool identity between arms is what makes
any future RQ4 contrast a selection-policy contrast rather than a
candidate-availability contrast. For Class-B specifically: with a
single open hypothesis the selector orders candidates by coverage,
cost, and test id — deterministic and valid, but pairwise
discrimination is structurally absent (see §6). No discrimination
capability is claimed for this configuration.

## 12. Admissibility rules

Windows: ≥20 NSE_CM sessions each (24/24 measured), 0 UNKNOWN
intersections, GOLDAUG2023 `trade_date` presence in both windows
(24 diagnostic / 20 held-out dates; presence only, never prices),
strict non-overlap, no interpolation/fill, no outcome-dependent
selection, no threshold tuning. Benchmark admissibility (branch
reachability, non-degenerate action, valid instruments) is proven
structurally by hand-built contract tests, not by market outcomes.
Any failure → "protocol amendment required", never silent substitution.

## 13. Reproduction-check semantics

One window-pair; n=1 execution per arm per window for future claims.
Each deterministic configuration may be repeated once, verified by
trajectory fingerprint equality, labelled REPRODUCTION CHECK.
Reproduction is not scientific replication (deferred to E3-D); n is
never inflated with duplicate deterministic runs, and trades/sessions
are never independent samples (E3-A §4).

## 14. Leakage and information-boundary rules

Held-out data influences nothing diagnostic (E3-A §7 inherited).
Benchmarks: TargetObservation only, AVAILABLE-checked VIX, missing
never filled, configured instruments only, no EnvironmentState, no
evaluator internals, no future data (verified by boundary tests).

## 15. External benchmark resources (deferred, not integrated)

- FinRL → future candidate autonomous/RL trading-agent
  implementations and methodology reference.
- FinQA → future financial numerical-reasoning evaluation.
- TAT-QA → future text+table financial-reasoning evaluation.
- ConvFinQA → future multi-turn financial-reasoning/consistency
  evaluation.
- FinanceBench → future evidence-grounded financial-reasoning
  evaluation.

Future integration needs a separate protocol (task interface,
information boundary, leakage controls, scoring, experimental unit,
Indian-environment relationship). No E3-C result depends on these
resources; none was read, run, or tuned against here.

## 16. Unresolved and deferred items

Class C autonomous target (dependency-gated); trend/mean-reversion
admission criteria; E3-D replication design and statistical pipeline;
`None`-metric missingness policy for future tests; buy-once marginal
resolving power beyond hold (E3-C may drop it only with written
rationale — not dropped here).

## 17. Scientific-integrity audit (E3-C self-check, recorded)

1. Identities frozen (manifest + §5). 2. Constants frozen (§4, untuned).
3. Constants outcome-independent (§3–§4 selection basis). 4–6. Mechanism,
binding, and provider mapping pre-registered (§6–§7) with Amendment-1
independence statement; H-concentration removed per audit with its
rejection preserved in §6 (no history rewriting). 7–8. F sequence frozen with exact stopping
semantics; pool identical across arms (§8, §10–§11); single-hypothesis
D=0 stated honestly with RQ4 discrimination deferred to E3-D. 9–10. Windows
strictly separated; held-out cannot influence diagnosis (§3, §14).
11–12. Reproduction labelled, not replication; trades never samples
(§13). 13. Stubs separated from benchmarks (§5; failure stubs stay in
tests). 14. Boundary verified by test (§14). 15. Class C honestly
deferred (§16 + §2 of E3-B). 16. E0–E2 semantics unchanged (diff-gated).
17. No circular construction (§5 independence + §6 derivation; the
removed D=1 claim is documented as rejected, not hidden). 18. Zero result language (this document contains no
outcomes). 19. Manifest reconstructs the protocol (single file +
fingerprints). 20. Hostile-reviewer test: every choice cites either a
pre-existing convention or an explicit design convention marked
uncalibrated — no silent post-hoc choice survives §4, §6, §12.
