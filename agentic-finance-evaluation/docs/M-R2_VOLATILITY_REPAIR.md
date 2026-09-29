# M-R2 — Volatility-Blind Controlled Repair: REJECT (honest negative)

CONTROLLED-KNOWN-MECHANISM. Engineering validation of the memory repair
path, not natural-market discovery. Protocol pre-registered in
`configs/controlled_repair/mr2_protocol.yaml` (VIX-only window selection).

## Protocol

Agent `volatility-blind-benchmark@1.0` (`benchmarks/volatility_blind.py`):
fixed BUY 1.0 RELIANCE:EQ every cash-available session, ignoring VIX.
Diagnostic 2020-01-01..2020-06-30 (77 HIGH sessions); held-out
2022-01-01..2022-06-30 (16 HIGH sessions, strictly later). Universe
RELIANCE:EQ, ₹100k, 5 bps, strict PIT. Repair: `hold_all` scoped to
vix_band [25, ∞), compiled from taxonomy `volatility` + vix>25 trigger.
Primary target `high_vix_buy_count` DECREASE; tolerances return/drawdown
0.05; bootstrap block-5/2000/seed 20260929, lower>0 required both
windows; coverage ≥10 fires.

## Results

Behavioural repair worked exactly as designed: high-VIX BUYs 31→2
diagnostic and 6→2 held-out; 30 fires (≥10); scope-exact (LOW/MID flow
untouched); shadow reproduced base records bit-identically; policy
fingerprint preserved; rollback/persistence stages unreached (no admission).

Gate: **REJECT**. Diagnostic cumulative return 0.2805 → 0.1085
(Δ −0.172, trips 0.05 tolerance). Held-out return 0.0768 → 0.0698
(within tolerance). Bootstrap diagnostic CI entirely negative
(mean −139.9); held-out straddles zero.

## Diagnosis of the failure

59 of 77 HIGH sessions fall in the Apr–Jun rebound, not the March crash:
suppression forfeits recovery exposure (base +28% by buying the bottom
through the rebound). Volatility blindness was profitable in this window;
the repair is genuinely harmful here. The gate functioned as designed —
suppression without quality is refused (E4-E discipline). No gate
weakening, no benchmark tuning, no admission. Artefacts:
`data/controlled_repair/MR2-20260929/` (base, verification, analysis,
validation report, audit, manifest).
