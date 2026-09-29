# M-R3 — Loss-Chasing Controlled Repair: NSF (honest negative)

CONTROLLED-KNOWN-MECHANISM. Engineering validation of the memory repair
path, not natural-market discovery. Protocol pre-registered in
`configs/controlled_repair/mr3_protocol.yaml`.

## Protocol

Agent `loss-chasing-benchmark@1.0` (`benchmarks/loss_chasing.py`):
after each consecutive portfolio-value decline, BUY quantity scales as
5·2^n (affordability-capped); normal size 5.0 otherwise. Diagnostic
2020-01-01..2020-06-30; held-out 2022-01-01..2022-06-30. Repair:
`max_quantity{cap:5.0}` (M-R3 vocabulary extension; cap equals normal
size so only escalation binds). Primary target `max_post_loss_quantity`
DECREASE; tolerances return/drawdown 0.05; bootstrap block-5/2000/seed
20260929, lower>0 required; coverage ≥5 escalations.

## Results

Behavioural repair worked: escalation events 4→0 diagnostic, 2→0
held-out; max post-loss quantity 10→5 both windows; 10 fires (≥5);
`_decide` ACCEPTED (target improved both windows, no tripped tolerance,
no new violations, no inactivity — inactivity 0.91→0.88).

Gate: **NSF**. Paired block-bootstrap CIs straddle zero both windows
(diagnostic mean −0.94 CI [−6.64, +4.45]; held-out mean −4.08 CI
[−15.66, +2.26]). Escalation events are rare (4 and 2); the real target
effect is economically indistinguishable from zero at 95% confidence.
Per protocol: NOT SUFFICIENT FOR SCIENTIFIC CLAIM. No admission, no
weakening, no tuning. Artefacts:
`data/controlled_repair/MR3-20260929/`.
