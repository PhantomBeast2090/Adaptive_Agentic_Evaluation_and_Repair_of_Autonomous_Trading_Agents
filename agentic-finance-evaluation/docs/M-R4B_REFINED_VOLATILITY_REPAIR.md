# M-R4B — Drawdown-Gated Volatility Repair: REJECT (honest negative)

CONTROLLED-KNOWN-MECHANISM, versioned separately (M-R2 REJECT stands).
Protocol pre-registered in `configs/controlled_repair/mr4b_protocol.yaml`
BEFORE evaluation: same agent/windows/universe/costs/metrics/tolerances/
statistics as M-R2; only the trigger is refined to a mechanistically
motivated conjunction — suppress accumulation while high VIX coincides
with an existing underwater position:

```text
trigger: vix > 25 AND drawdown > 0.05
drawdown = max(0, -unrealized_pnl / total_equity), own-portfolio only,
           stateless, PIT-safe, fail-closed on unusable inputs
```

New trigger field `drawdown` added to schemas + control-plane resolver
(additive; M-R2 artefacts untouched). Threshold 0.05 is a conventional
fixed value, not searched. No window/threshold/outcome tuning.

## Results

Behavioural effect real but narrow: high-VIX buys 31→25 diagnostic,
6→6 held-out; 53 fires (trigger uses observation-lag prior VIX while the
custom metric counts current-session VIX — a pre-registered measurement
nuance, no post-hoc change). Coverage 53/10 passes. Policy preserved.

Gate: **REJECT**. Diagnostic return 0.2805→0.1631 (trips 0.05
tolerance); bootstrap diagnostic CI fully negative (mean −95.45).
Held-out economics neutral (mean +0.07, CI straddles zero).

## Diagnosis

The drawdown gate fires through the crash AND the early rebound
(drawdown stays elevated while prices recover), so rebound forfeiture
persists in attenuated form. Refining the trigger from "high VIX" to
"high VIX + underwater" does not rescue the economics: any suppression
rule active across Mar–Jun 2020 forfeits the recovery that made
volatility blindness profitable in this window. Reported separately as
required; no admission; no further volatility variants.
Artefacts: `data/controlled_repair/MR4B-20260930/`.
