# M-R5C — Adaptive Repair Report

Verdict: **ACCEPT** (adaptive selection passed all gates)

Mechanism: exposure (support 80)
Selected: `M-R5C-C-exposure_cap-max_names_held=2`
Rejected: 5 of 7

## Candidates

- `M-R5C-C-exposure_cap-max_names_held=1`: target_reduction=-2.00, CI=(-2.00,-2.00), fires=80, final=511083, suppression=1.000
- `M-R5C-C-exposure_cap-max_names_held=2`: target_reduction=-1.00, CI=(-1.00,-1.00), fires=80, final=524383, suppression=1.000
- `M-R5C-C-quantity_reduction-fraction=0.25`: target_reduction=0.00, CI=(0.00,0.00), fires=80, final=508589, suppression=1.000
- `M-R5C-C-quantity_reduction-fraction=0.5`: target_reduction=0.00, CI=(0.00,0.00), fires=80, final=517179, suppression=1.000
- `M-R5C-C-per_session_order_cap-max_orders=1`: target_reduction=-2.00, CI=(-2.00,-2.00), fires=80, final=511083, suppression=1.000
- `M-R5C-C-per_session_order_cap-max_orders=2`: target_reduction=-1.00, CI=(-1.00,-1.00), fires=80, final=524383, suppression=1.000
- `M-R5C-C-max_quantity-cap=30.0`: target_reduction=0.00, CI=(0.00,0.00), fires=0, final=534358, suppression=0.000

## Rejections

- `M-R5C-C-exposure_cap-max_names_held=1`: {'rejected': ['economic regression beyond tolerance']}
- `M-R5C-C-quantity_reduction-fraction=0.25`: {'rejected': ['bootstrap CI does not exclude null', 'economic regression beyond tolerance']}
- `M-R5C-C-quantity_reduction-fraction=0.5`: {'rejected': ['bootstrap CI does not exclude null']}
- `M-R5C-C-per_session_order_cap-max_orders=1`: {'rejected': ['economic regression beyond tolerance']}
- `M-R5C-C-max_quantity-cap=30.0`: {'rejected': ['repair never fired', 'bootstrap CI does not exclude null']}

Selection: {'final_value': 524382.9485484995, 'selected': True, 'suppression_rate': 1.0, 'target_reduction': -1.0}

Policy fingerprint: `0a1759c48d686724…`
Manifest fingerprint: `e3e383060dc3d3b6…`
Persistence: REPRODUCED, Rollback: RESTORED
