# M-R5A — Adaptive Repair Report

Verdict: **ACCEPT** (adaptive selection passed all gates)

Mechanism: loss_chasing (support 35)
Selected: `M-R5A-C-max_quantity-cap=5.0`
Rejected: 6 of 9

## Candidates

- `M-R5A-C-max_quantity-cap=5.0`: target_reduction=-37.50, CI=(-47.50,-27.50), fires=35, final=491617, suppression=0.357
- `M-R5A-C-max_quantity-cap=10.0`: target_reduction=-25.00, CI=(-33.57,-16.43), fires=21, final=488738, suppression=0.214
- `M-R5A-C-max_quantity-cap=20.0`: target_reduction=-10.00, CI=(-15.71,-4.29), fires=7, final=485407, suppression=0.071
- `M-R5A-C-quantity_reduction-fraction=0.25`: target_reduction=-35.00, CI=(-43.57,-26.43), fires=98, final=495788, suppression=1.000
- `M-R5A-C-quantity_reduction-fraction=0.5`: target_reduction=-25.00, CI=(-30.71,-19.29), fires=98, final=491575, suppression=1.000
- `M-R5A-C-block_action-side=BUY`: target_reduction=-37.50, CI=(-47.50,-27.50), fires=98, final=500000, suppression=1.000
- `M-R5A-C-block_action-side=SELL`: target_reduction=0.00, CI=(0.00,0.00), fires=0, final=483150, suppression=0.000
- `M-R5A-C-exposure_cap-max_names_held=1`: target_reduction=0.00, CI=(0.00,0.00), fires=0, final=483150, suppression=0.000
- `M-R5A-C-exposure_cap-max_names_held=2`: target_reduction=0.00, CI=(0.00,0.00), fires=0, final=483150, suppression=0.000

## Rejections

- `M-R5A-C-quantity_reduction-fraction=0.25`: {'rejected': ['normal-session behaviour altered']}
- `M-R5A-C-quantity_reduction-fraction=0.5`: {'rejected': ['normal-session behaviour altered']}
- `M-R5A-C-block_action-side=BUY`: {'rejected': ['normal-session behaviour altered', 'full inactivity']}
- `M-R5A-C-block_action-side=SELL`: {'rejected': ['repair never fired', 'bootstrap CI does not exclude null']}
- `M-R5A-C-exposure_cap-max_names_held=1`: {'rejected': ['repair never fired', 'bootstrap CI does not exclude null']}
- `M-R5A-C-exposure_cap-max_names_held=2`: {'rejected': ['repair never fired', 'bootstrap CI does not exclude null']}

Selection: {'final_value': 491616.69991925, 'selected': True, 'suppression_rate': 0.35714285714285715, 'target_reduction': -37.5}

Policy fingerprint: `d7b6eae48f079fea…`
Manifest fingerprint: `b2843fa7ffc50648…`
Persistence: REPRODUCED, Rollback: RESTORED
