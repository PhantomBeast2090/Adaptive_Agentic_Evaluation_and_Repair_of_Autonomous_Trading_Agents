# TERMINAL RESEARCH ASSESSMENT — Adaptive Agentic Evaluation and Repair of Autonomous Trading Agents

Status: experimental branch CLOSED. No I3. No new ML model. No new support
search. No threshold relaxation. No repair attempt on unvalidated
candidates. This document is the terminal scientific record (commits
`532e071` implementation/docs, `fd630a6` frozen evidence).

## 1. Milestone evidence ledger (E0 → I2)

| Milestone | Question | Dataset / support | Representation / target | Model / miner | Result → falsification | Verdict | Class |
|---|---|---|---|---|---|---|---|
| E0–E2 | Contracts, baseline evaluator, diagnostics | Indian env, PIT contract | Deterministic episodes | — (infrastructure) | Built + frozen | DONE | — |
| E3–E4 | Repair loop machinery (context, gate, MemoryStore, throttle vocab) | Synthetic/controlled | LearnedContext lifecycle | DeterministicRuleProvider | Machinery works; E4-E: suppression≠quality established | DONE | — |
| E5A | Baseline attribution | 106 BUY-only exec, 0 SELL | V1 14f, MAE/fwd | B1 baseline | NULL | NULL | B (single-action, single-regime) |
| M1 | Logistic diagnosis on E5A | 106 rows | V1/V2 | Logistic vs B0 | VALID/TEST beats B0 BUT permutation also beats B0 → prevalence artefact | M1-NULL | B |
| M2 | Capacity: HGB/TabPFN | E5A windows | V1/V2 | HGB; TabPFN BLOCKED (no token) | M2-NULL (representation) / UNTESTED (capacity) | NULL/BLOCKED | B |
| M3/MLF | Foundation models (Chronos-2/TimesFM-3) | E5A | Forecast legs + V1/V2 | Chronos-2/TimesFM-3 adapters + miner | 106/106 available, 0 candidates; miner kills ~948/950 at N≥15 | NULL | B |
| M4 | Sequence features | E5A combined V3 | 24 seq features | R0/R1 ablation | M4-NULL, branch stopped | NULL | B |
| P2/regret | BUY-vs-HOLD regret target | — | hold_3d − fwd_3d | — | Identically zero (exec = T-close): environment semantics | Formulation NULL | — (not support; semantics) |
| TIMING | t+1 entry-timing counterfactual | 98 labelled, adv 16/98 | timing_regret, band 0.01 | Frozen miner, universe 5911 | 0 candidates; permutation 5v0 (real worse than chance) | CASE B NULL | B |
| F0 | ChoiceAccumulator v1.0 diversity | 142+65 sess; 6+5 non-HOLD exec | — | — | Minor share 2.1%/3.1% vs 5%; single quantity | GATE NOT MET | B |
| F0R | Rationale-first diversity fix | 142/65 sess | — | — | Conditional pass (F0R-B marginal 4.6 vs 5.0 recorded) | PASS* | B |
| F1 | PIT attribution layer | F1R-A 210 rows/102 exec; F1R-B 99/53 | Forward/MAE/MFE/hold/opp | Attribution engine (cached shim 18/18 leg-identical) | Infrastructure only | DONE | — |
| F2 | Taxonomy mining | TRAIN 119 / VALID 36 / TEST 0 labelled | R1 (45num+4cat), MAE/fwd | Frozen miner, universe 7149 | 5+5 candidates; TEST structurally empty; perm parity; all-MAE RELIANCE-only; vacuous VALID | F2-NULL | B |
| F2R | Calendar-only re-split rescue | TRAIN 119 / VALID 6 / TEST 30 SELL-only | Same | Same, seed 20260926 | 0 validated; TEST-confirmation failure binding; perm parity; BUY→SELL segregation | F2R-NULL | B |
| F3 | v1.1 ladder/exits/pause overlap | F3A 178 rows/54 lab; F3B 85/32 | — | Mining deliberately NOT run | BUY episode → dead gap → SELL episode; no 3-way split with VALID≥10 | SUPPORT-STOP | B |
| G1 | 6-name multi-asset + rotation | G1A 258 rows/88 lab; G1B 124/0 (all HOLD) | — | Not run (gate-gated) | TEST SELL-only; regime→action segregation persists | G1-SUPPORT-FAIL | B |
| H0 | Capital-state variation | 4×189 sess; 26/189 disagree, ALL in TRAIN | Paired-date clusters | Not run | VALID 0, TEST 0 contrasts | H0-SUPPORT-FAIL | B |
| I1 | Threshold-boundary perturbation (6 cells) | 46/19/18 contrasts (gates 15/10/20) | Paired-date × 6 cells | Not run (TEST 18<20) | VALID fixed (19); TEST misses by 2; W1-T3 structural zero proven | I1-SUPPORT-FAIL | B |
| I2/K1 | 18-cell factorial completion | 56/32/22 contrasts; 2458 labelled (1743/333/382) | R1 V1+V2+seq; MAE/fwd | Frozen miner + permutation + transfer | 5v5 parity both targets; strongest survivors blocked (confinement / parity) | **I2-NULL** | **C** |

Class B = support/identifiability failure (miner never legitimately testable).
Class C = adequate support, frozen protocol executed, no validated mechanism.
Only I2 is Class C. Nothing is conflated.

## 2. I2 forensic audit (verified terminally)

- K1 selected before outcome exposure: audit doc + selection.json mtimes
  precede first attribution.json; mine results land a day later. Winner
  freeze (spec.json + selection.json) written before I2f.
- Y-firewall enforced: run_i2.py imports agent+baseline+contracts only
  (import-tested); attribution/ml imports exist solely in
  run_i2_diagnosis.py (the authorised outcome stage).
- 2458 labelled rows: CSV `mae < -0.01` reproduces miner counts/rates
  exactly (1743/333/382 @ .685/.739/.605); spot attribution↔CSV parity
  307/307.
- TRAIN/VALID/TEST thirds pairwise disjoint (verified); pooled across
  windows by pre-registered rule, unmoved.
- Cached attribution: F1-proven 18/18 leg-identical shim, reused unchanged.
- Miner thresholds N≥15/Δ≥0.02/top-5 byte-identical in frozen module;
  permutation seed 20260926 with identical derange protocol (diffed vs
  run_f2: only added reporting line).
- One disclosed shim: memoization of per-row condition expansion
  (~7h/call → ~6min/call at I2 scale); bit-identity proven by
  test_i2_diagnosis.py::test_shim_equivalence; frozen files untouched.
- No MemoryStore/context contact (memory/ dirs empty; import-tested); no
  repair code path executed. Frozen-path diff c7ba867..HEAD: clean.

## 3. YESBANK forensic classification (frozen artefacts, no rerun)

H1 `[holdings_value=low, instrument=YESBANK:EQ]`: TRAIN 60@1.0, VALID
9@1.0, TEST 28@0.786 (+0.181), transfer pass — yet experiment-level
permutation parity + single-instrument confinement. Classification:

- **Primarily instrument identity/proxy behaviour.** YESBANK pooled
  adverse rate 0.823 vs 0.539–0.729 for all other names; uniformly worst
  in every split (train .836 / valid .789 / test .810). A fixed name
  attribute, not a context-dependent failure mechanism.
- **Market/regime structure.** YESBANK TRAIN rows span 33 dates across
  both windows' stress episodes; TEST rows (22 dates, 57/58 SELL) are the
  crash-liquidation exit episode. Adversity concentrates where the market
  concentrates it.
- **Decisive non-transfer of the lift:** on TEST, H1 (0.786) UNDERPERFORMS
  the bare YESBANK marginal (0.810). The holdings low-band lift
  (0.836→1.000 on TRAIN) is a TRAIN-local filter with zero out-of-sample
  value beyond the name tag.
- **Not a concentration mechanism in any repairable sense:** YESBANK
  median pre-holdings (38.5k) EXCEED others' (31.9k); nothing about the
  condition maps to the throttle/breadth repair vocabulary. There is no
  legitimate memory principle to admit ("avoid YESBANK when holdings low"
  is a strategy rewrite, CASE C, correctly unreached).
- Verdict on H1: genuine but insufficiently falsifiable structure —
  a real name effect that fails two frozen falsification criteria.
  Recorded as unevaluated candidate, never a mechanism. No rescue.

## 4. Terminal ledger

### Demonstrated

- PIT-safe deterministic Indian-market evaluation (T-close execution
  semantics audited; P2 identity proven structural).
- Decision attribution at scale (frozen engine; 36-branch/8.6k-row I2f;
  byte-level reproducibility C0-W1 == G1-A).
- Behavioural intervention machinery + context/MemoryStore lifecycle
  (built, gated, tested — E3/E4).
- Deterministic reproducibility (bit-identical reruns at branch and
  experiment level; fingerprint discipline throughout).
- Behavioural diversity on demand (18 deterministic cells, all action
  classes, quantities, exits, 6 instruments, 2 windows).
- Support construction (H0→I1→I2: 0/0 → 46/19/18 → 56/32/22 paired
  contrasts; positivity violation converted to overlap by design).
- Diagnostic execution under adequate support (2458 labelled rows through
  the frozen miner, both targets).
- Falsification discipline (permutation parity applied terminally against
  attractive candidates; single-instrument rule applied; validation-review
  correctly distinguished from held-out confirmation).

### Not demonstrated

- Validated recurring failure mechanism (none survived falsification).
- LearnedContext admission for a discovered mechanism (gate never met).
- Quality-improving repair; held-out repair verification; profitability
  improvement; autonomous self-repair; generalisation. The loop's second
  half is architecturally ready and empirically unreached.

### Unknown (genuinely open, not foreclosed)

- Whether mechanisms exist outside the tested formulation (other miners,
  schemas, targets, horizons) — untested, not disproven.
- Whether the overlap-population restriction (HIGH/transition episodes)
  hides mechanisms that only appear in calm regimes — structural blind
  spot of all regime-gated designs, disclosed.
- Whether a validated mechanism, if found, would repair via memory
  (the thesis's second half remains an untested conditional).
- Made UNLIKELY (not unknown): that support was the only blocker (I2
  supplied it); that threshold relaxation finds mechanisms (parity
  analysis); that the YESBANK structure is repairable (non-transfer).

## 5. "Did ML fail?" — No.

Precise statement: the tested diagnostic ML/mining formulation produced
no validated failure mechanism under the frozen protocol, even after I2
supplied adequate behavioural overlap. This establishes: (a) the
conditional-miner + R1 + MAE/forward formulation does not validate
mechanisms on this agent/environment overlap population; (b) more data,
assets, windows, cells, and support do not change that verdict under this
formulation. It does NOT establish: ML-in-general cannot diagnose trading
agents; no mechanisms exist; the repair thesis is false. The diagnostic
instrument was tested and returned NULL — instruments returning NULL is
what they are for.

## 6. "Why did we not reach repair?"

Because the protocol requires diagnosis → falsification → validated
mechanism → MemoryStore admission → repair → held-out verification, and
no candidate crossed the admission threshold. An untouched MemoryStore is
a protocol success: the gate did exactly what it was built to do when the
strongest candidates (H1/H5) failed falsification. Repairing on H1 would
have meant throttling YESBANK on the basis of a name tag that
underperforms its own marginal out-of-sample — the precise failure mode
the gate exists to prevent.

## 7. Thesis evaluation: **B** — partial framework demonstration with negative diagnostic result

- Not A (no repair demonstrated — the loop never closed).
- B, grounded: evaluation + attribution + support-construction +
  diagnosis-under-support + falsification all demonstrated and frozen;
  diagnostic result honestly negative (Class C).
- The defensible publication vehicle is C-flavoured (methods +
  falsification + negative result), reporting a B-state project. D is
  unnecessary: B is already a complete, honest scientific unit.
- Recommended paper structure (structure only): (1) problem: external
  memory repair of trading agents; (2) frozen evaluation/attribution
  substrate; (3) the support problem: positivity formalism + F/G/H ledger
  (Class B chain); (4) I1/I2: factorial overlap design, Y-free selection
  protocol with validity argument; (5) Class-C NULL: miner results,
  permutation parity, YESBANK autopsy; (6) boundary statement: what was
  shown, what remains conditional; (7) artefacts: frozen traces,
  fingerprints, reproduction paths.

## 8. Closure

No I3. No new ML model. No new support search. No threshold relaxation.
No repair attempt based on unvalidated candidates. The experimental branch
is closed; the ledger above is the terminal scientific record.
