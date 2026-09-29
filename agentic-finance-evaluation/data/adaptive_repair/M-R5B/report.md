# M-R5B — Adaptive Repair Report

Verdict: **ACCEPT** (adaptive selection passed all gates)

Mechanism: overtrading (support 80)
Selected: `M-R5B-C-per_session_order_cap-max_orders=1`
Rejected: 2 of 4

## Candidates

- `M-R5B-C-per_session_order_cap-max_orders=1`: target_reduction=-30.00, CI=(-30.00,-30.00), fires=80, final=1000349, suppression=1.000
- `M-R5B-C-per_session_order_cap-max_orders=2`: target_reduction=-20.00, CI=(-20.00,-20.00), fires=80, final=1001397, suppression=1.000
- `M-R5B-C-block_action-side=BUY`: target_reduction=-40.00, CI=(-40.00,-40.00), fires=80, final=1000000, suppression=1.000
- `M-R5B-C-block_action-side=SELL`: target_reduction=0.00, CI=(0.00,0.00), fires=0, final=1003843, suppression=0.000

## Rejections

- `M-R5B-C-block_action-side=BUY`: {'rejected': ['full inactivity']}
- `M-R5B-C-block_action-side=SELL`: {'rejected': ['repair never fired', 'bootstrap CI does not exclude null']}

Selection: {'final_value': 1000349.37482485, 'selected': True, 'suppression_rate': 1.0, 'target_reduction': -30.0}

Policy fingerprint: `027a7cfd735a3375…`
Manifest fingerprint: `aefe4d90c54ab452…`
Persistence: REPRODUCED, Rollback: RESTORED
