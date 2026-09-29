# M-R5D — Adaptive Repair Report

Verdict: **ACCEPT** (adaptive selection passed all gates)

Mechanism: volatility (support 45)
Selected: `M-R5D-C-hold_all`
Rejected: 4 of 7

## Candidates

- `M-R5D-C-hold_all`: target_reduction=-30.00, CI=(-30.00,-30.00), fires=45, final=500760, suppression=0.429
- `M-R5D-C-exposure_cap-max_names_held=1`: target_reduction=0.00, CI=(0.00,0.00), fires=0, final=501148, suppression=0.000
- `M-R5D-C-exposure_cap-max_names_held=2`: target_reduction=0.00, CI=(0.00,0.00), fires=0, final=501148, suppression=0.000
- `M-R5D-C-per_session_order_cap-max_orders=1`: target_reduction=0.00, CI=(0.00,0.00), fires=0, final=501148, suppression=0.000
- `M-R5D-C-per_session_order_cap-max_orders=2`: target_reduction=0.00, CI=(0.00,0.00), fires=0, final=501148, suppression=0.000
- `M-R5D-C-quantity_reduction-fraction=0.25`: target_reduction=-22.50, CI=(-22.50,-22.50), fires=45, final=500857, suppression=0.429
- `M-R5D-C-quantity_reduction-fraction=0.5`: target_reduction=-15.00, CI=(-15.00,-15.00), fires=45, final=500954, suppression=0.429

## Rejections

- `M-R5D-C-exposure_cap-max_names_held=1`: {'rejected': ['repair never fired', 'bootstrap CI does not exclude null']}
- `M-R5D-C-exposure_cap-max_names_held=2`: {'rejected': ['repair never fired', 'bootstrap CI does not exclude null']}
- `M-R5D-C-per_session_order_cap-max_orders=1`: {'rejected': ['repair never fired', 'bootstrap CI does not exclude null']}
- `M-R5D-C-per_session_order_cap-max_orders=2`: {'rejected': ['repair never fired', 'bootstrap CI does not exclude null']}

Selection: {'final_value': 500760.3161764998, 'selected': True, 'suppression_rate': 0.42857142857142855, 'target_reduction': -30.0}

Policy fingerprint: `551555796777d374…`
Manifest fingerprint: `31c7f62e3354b971…`
Persistence: REPRODUCED, Rollback: RESTORED
