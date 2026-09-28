# G1 Behavioural Support Audit — Verdict: G1-SUPPORT-FAIL → G1-NULL

## 1-7. State, universe, agent, constants, observation, windows

HEAD `ba52463` at build; tree clean save gitlinks. Universe: top-6
2019-Q4 turnover among 617 complete-bars EQ names (YESBANK, ICICIBANK,
RELIANCE, SBIN, INFY, TCS) — outcome-blind, fingerprinted in
`data/frozen_traces/_g1/universe.json`. No NIFTY-50 membership dataset
exists in-repo (reported limitation; liquidity-rank substitute used).
Agent `multi-asset-choice@1.0` (v1.1 policy + rotation edge 0.02,
6 names, MAX_NAMES 4, MAX_ORDERS 6). Constants frozen in
`configs/choice_agent/g1.yaml` pre-run. Observation: existing slots
only (VIX, closes, cash, positions, exposure block). Windows G1-A
2020-01-01→2020-09-30, G1-B 2020-10-01→2021-03-31.

## 8-10. Behavioural distributions

G1-A (189 sess): HOLD 170 / BUY 9 / SELL 7 / mixed 3; quantities
{2.0×11, 1.0×72, flatten 6–11}; exposure 0–55%; 7 exits; minor 5.3%.
G1-B (124 sess): all HOLD — MID-regime desert (VIX MID-dominated).
Minor 0%.

## 11. VIX/action overlap

G1-A: LOW→BUY/HOLD, MID→HOLD (+rare trend-exit SELL), HIGH→SELL.
Within-regime overlap exists only marginally (mixed sessions 3).
G1-B contributes zero behaviour.

## 12. Portfolio-state/action overlap

Exposure/concentration tiers produce quantity variation (ladder
works); rotation fires (SELL+BUY pairs observed); but state overlap
across actions is thin — SELL states cluster in crash drawdown.

## 13. Split support (best candidate cut 02-10/02-28)

TRAIN 50 (48 BUY + 2 SELL) ✓≥45; VALID 16 (14+2) ✓≥15 both actions;
TEST 22 SELL-only ✗ (minor 0%). YESBANK thin (5 total). No cut
avoids this: executions segregate into pre-crash BUY / crash SELL
with a dead gap — identical in kind to F2R.

## 14. Gate result: FAIL

Minor-action share per split and mixed-action TEST fail; "no action
class confined to one isolated regime episode" fails (SELLs crash-
confined). Per §9/§18: STOP. No mining, no ML, no hypotheses.

## 15-17. Attribution/mining/falsification: not run (gate-gated)

Attribution traces (G1A 258 rows/88 labelled, G1B 124/0) persist as
measurement infrastructure for any authorised future branch.

## 18. Fingerprints

G1-A `c9c9c124…`, G1-B `80e71386…`; G1A `d9c48111…`, G1B `084219d0…`.

## 19. Tests

`tests/agents/test_g1.py` (5 passed: rotation, no-edge, parity,
determinism, identity). Regression chunks below.

## 20-21. Frozen-diff / MemoryStore / agent status

Frozen paths untouched (additive only). MemoryStore untouched. Agent
unmodified post-freeze.

## 22. Verdict: G1-SUPPORT-FAIL → G1-NULL

Multi-asset choice improved absolute support (88 labelled, 6 names,
mixed sessions) but did NOT break regime→action segregation — the
binding constraint identified in F2R. The thesis test remains
unpowered. No further variants without fresh authorisation.

## 23-24. Next milestone / authorisation needed

None authorised. Honest options: (a) close the choice-agent branch;
(b) authorise a fundamentally different overlap source (intraday?
no — data lacks it; stochastic policy? breaks fingerprints).
Recommendation: pause agent-variant work; the open question is now
explicitly whether deterministic regime-gated policies can EVER
yield overlapping support — current evidence says no.
