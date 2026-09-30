# M-R9 — Multi-Mechanism / Multi-Window Campaign: BOUNDED NULL

## Verdict

**NULL — 0/6 experiments admitted a repair.** No held-out construction
beyond diagnostic adjudication failures (held-out files exist only
where the pipeline reached that stage: none — no candidate passed
diagnostic adjudication in any experiment, so no held-out, MemoryStore,
persistence, rollback, or replication artefacts exist). Per the
pre-registered stopping rule the campaign is exhausted; no further
experiment was added.

## Design (frozen before execution)

Six contiguous diag→held→rep triples (3 months each), chronological,
mutually disjoint, all outside 2020, spread 2021–2026. Bank selected
from VIX prevalence + NSE calendar coverage only (≥40 sessions/window;
all triples 59–65). 2024 is absent from the NSE calendar, so the
pre-registered nearest-valid-shift rule moved R9-D/E/F off 2024 (R9-D
replication spans the gap to 2025Q1). R9-B overlaps the M-R6 held-out
window, which was never constructed — disclosed. Same agent, policy,
universe, costs, PIT/vintage, detectors, thresholds, generator,
compiler, bootstrap (`20260930/5000/0.05`) and tolerances as M-R6.
Broad serving; fixed generalized mechanism-relative adjudication
(`activity.py`); N0 sensitivity descriptive only; disclosure-only
multiplicity; 40-episode/experiment and 240-episode campaign budgets
(94 consumed).

## Per-experiment outcomes

| Exp | Regime | Sessions | Selected mechanism (support) | Also fired | Candidates | Statuses | Episodes |
|---|---|---|---|---|---|---|---|
| R9-A | normal-2021 | 61 | exposure (14) | — | 9/9 | 9 STATISTICAL_NULL | 19 |
| R9-B | elevated-2022 | 61 | none (full abstention) | — | 0 | — (controls NOT-APPLICABLE) | 1 |
| R9-C | transition-to-calm | 62 | exposure (34) | — | 8/8 | 8 STATISTICAL_NULL | 17 |
| R9-D | calm-2023-spanning-gap | 63 | exposure (57) | overtrading (10) | 9/9 | 6 SPECIFICITY_REJECT, 3 STATISTICAL_NULL | 19 |
| R9-E | later-2025 | 61 | exposure (15) | — | 9/9 | 6 SPECIFICITY_REJECT, 3 STATISTICAL_NULL | 19 |
| R9-F | recent-2026 | 59 | exposure (48) | overtrading (24) | 9/9 | 6 SPECIFICITY_REJECT, 3 STATISTICAL_NULL | 19 |

Totals: 44 candidates (44 compiled, 0 refused beyond generation;
R9-C generated 8 — two distinct BUY quantities yield two
`max_quantity` caps by the frozen rule), 26 STATISTICAL_NULL, 18
SPECIFICITY_REJECT, 0 ADMISSIBLE. Table 3 (admitted) is empty by
construction. Controls: all REFUSED/REJECTED where applicable.

## Mechanism-diversity finding (honest)

Exposure was selected in all five non-abstaining windows (supports
14–57). Overtrading fired twice (10, 24) but lost on support both
times. Loss-chasing, volatility, and drawdown never fired on any
natural trajectory tested (M-R6 through M-R9: nine diagnostic windows).
The campaign therefore answers the diversity question negatively for
this agent/policy/universe: distinct natural mechanisms did not
materialise, so mechanism-specific repair compatibility beyond exposure
remains demonstrated only in controlled conditions (M-R5A–E). This is a
finding about the agent-environment pair, not a flaw in the detectors
(thresholds frozen; abstentions recorded, never overridden).

## Rejection anatomy

- STATISTICAL_NULL (26): candidates specific under the fixed
  mechanism-relative mask (including all R9-A/R9-C) with bootstrap CIs
  including null — the M-R8 power pattern reproduced at lower supports.
- SPECIFICITY_REJECT (18): order caps and quantity reductions altering
  mechanism-inactive sessions through portfolio-state path dependence —
  the M-R8 trajectory-specificity pattern reproduced (R9-D/E/F).
- No POLICY_CHANGED, SHADOW_FAILED, SAFETY_REJECT, INACTIVITY_REJECT,
  ECONOMIC_GATE_REJECT, or NORMALITY_REJECT occurred (NORMALITY_REJECT
  reserved for N0-gated designs).

## Artefacts

`data/adaptive_repair/M-R9/`: `protocol.yaml`, `window_bank.json`,
`summary.json`, per-experiment dirs (diagnosis, candidates,
candidate_results with full §13 readings vectors, adjudication with
statuses, freeze, result, audit, controls), `tables/table{1,2,4,5}.json`
(Table 3 empty), `figures/figure{1,3,4a,4b,5,6}.png` with
`skipped.json` (Figures 2, 7 skipped: nothing admitted).

## Interpretation

M-R9 extends the bounded NULL from one trajectory (M-R6/M-R8) to six
independent windows: the machinery detects (5/6), synthesises (44),
verifies, and fails closed every time, while the agent's natural
behaviour yields only exposure (and twice overtrading, unselected).
The binding constraints are unchanged in kind — bootstrap power at low
support, trajectory specificity for suppressive actions — and the
campaign adds the prevalence result: non-exposure mechanisms are absent
from nine natural diagnostic windows for this configuration.
