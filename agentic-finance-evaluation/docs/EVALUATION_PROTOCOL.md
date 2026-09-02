
# Evaluation Protocol
- Static Baseline
- Adaptive Evaluation
- Diagnosis
- Concordance Gate
- Targeted Repair / Intervention
- Re-evaluation
- Side-effect Detection
- Holdout Evaluation

## Implemented MVP Components

- Module A: deterministic vulnerability discovery from trajectory metrics.
- Module B: blinded diagnosis interface with deterministic mock behaviour for tests.
- Concordance checker: intervention proceeds only when discovery and diagnosis agree.
- Module C: deterministic intervention payload generation from concordant findings.
- Module D: deterministic pre/post repair comparator with optional holdout validation.

## Re-evaluation Rule

Repair success requires:

- the targeted vulnerability metric to fall below its configured threshold;
- no configured regression side effects to be detected;
- holdout validation to pass when a holdout trajectory is supplied.

These MVP checks are deterministic evidence checks, not statistical proof of the
research hypothesis.
