# F3 Behavioural + Support Audit — Verdict: SUPPORT-STOP before mining

## F3b behavioural validation (v1.1 mechanisms observed live)

F3-A (142 sess): HOLD 124 / BUY 11 / SELL 7; quantities {2.0×3,
1.0×48, 6.0×3 flatten}; exposure 0–53%; 3 full exits. Minor share
7/142 = 4.93% vs 5% gate — narrow miss, recorded not redefined.
F3-B (65 sess): HOLD 53 / BUY 9 / SELL 2 / mixed 1; quantities
{2.0×8, 1.0×24}; exposure 0–59%; exits 0. Minor 1.5–4.6%.
Staged trim/flatten, ladder taper, and cash pause all fire in-crash;
MID-regime F-VOL guard holds (zero violations). Determinism,
no-short, cost identity, BINDING honesty all verified.

## F3c attribution (frozen engine, cached shim)

F3A-20260926: 178 rows, 54 labelled (33 BUY + 21 SELL, 18/18/18
instruments), span 2019-11-22→2020-03-13. F3B-20260926: 85 rows, 32
labelled (27 BUY + 5 SELL). MAE adv 33/22; fwd adv 24/8.

## F3d support audit — FAILS, mining not run

Execution timeline is episodically segregated: 33 BUYs pre-2020-01-15
→ dead gap (no executions of any kind through early March) → 21
SELLs post-2020-03-01. No three-way temporal split can populate a
labelled VALID (needs ≥10): any VALID carved from the BUY episode
leaves TEST SELL-only with no overlap; any VALID from the SELL
episode leaves TEST empty. TEST≥20 is satisfiable only as
SELL-only (21 rows). Two-action overlap within ≥2 VIX regimes —
the core F3 requirement — does not exist in the traces.

## Verdict

**STOP before F3e.** Per F3d rule and §16: the support failure is
reported, not routed around. Contributing cause: regime-gated
deterministic policies produce non-overlapping behavioural episodes
(accumulate / freeze / liquidate); temporal confirmation needs
overlap that episodic behaviour structurally withholds. This is a
finding about choice-agent design, not a miner failure.
No hypotheses, no validation, no repair. MemoryStore untouched,
agent frozen at v1.1, no further variants.
Artefacts: F3-A/B baselines, F3A/B attribution, this report.
