# M-R5E — Adaptive Repair Report

Verdict: **ACCEPT** (adaptive selection passed all gates)

Mechanism: drawdown (support 20)
Selected: `M-R5E-C-cooldown_after_loss-sessions=1`
Rejected: 0 of 5

## Candidates

- `M-R5E-C-drawdown_risk_scaler`: target_reduction=-17.50, CI=(-27.71,-7.29), fires=49, final=459780, suppression=0.583
- `M-R5E-C-quantity_reduction-fraction=0.25`: target_reduction=-29.17, CI=(-41.67,-16.67), fires=49, final=465617, suppression=0.583
- `M-R5E-C-quantity_reduction-fraction=0.5`: target_reduction=-20.42, CI=(-29.17,-11.67), fires=49, final=462302, suppression=0.583
- `M-R5E-C-cooldown_after_loss-sessions=1`: target_reduction=-32.08, CI=(-45.83,-18.33), fires=49, final=468932, suppression=0.583
- `M-R5E-C-cooldown_after_loss-sessions=2`: target_reduction=-32.08, CI=(-45.83,-18.33), fires=49, final=468932, suppression=0.583

## Rejections


Selection: {'final_value': 468931.7782460001, 'selected': True, 'suppression_rate': 0.5833333333333334, 'target_reduction': -32.083333333333336}

Policy fingerprint: `d7b6eae48f079fea…`
Manifest fingerprint: `6075700fd2eaf328…`
Persistence: REPRODUCED, Rollback: RESTORED
