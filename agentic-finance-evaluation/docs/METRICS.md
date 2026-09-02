
# Metrics
- Failure Detection
- Evaluation Coverage
- Evaluation Efficiency
- Agent Quality
- Repair Effectiveness
- Generalization
- Cost

## MVP Deterministic Metrics

- Conditional post-loss drawdown: maximum drawdown observed after a losing step.
- Conditional position-exposure ratio: post-loss exposure divided by pre-loss exposure.
- Cumulative return: final portfolio value relative to inferred initial value.

## MVP Repair Interpretation

- `MITIGATED`: target metric improved meaningfully and fell below threshold.
- `IMPROVED_NOT_MITIGATED`: target metric improved but remains above threshold.
- `REGRESSED`: target metric worsened after intervention.
- `UNCHANGED`: target metric did not meaningfully change.
- `NO_BASELINE_VULNERABILITY`: pre-intervention metric was not above threshold.

Repair-effectiveness claims must also account for side effects and holdout
validation.
