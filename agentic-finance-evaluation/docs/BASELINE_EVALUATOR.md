# E1 — Deterministic Baseline Evaluator

Status: measurement substrate (milestone E1). Deterministic, non-adaptive.
No diagnosis, no test selection, no repair, no learning, no LLM.

Package: `evaluation/baseline/`. Wraps the frozen Indian multi-asset
environment and the frozen E0 contracts; modifies neither.

## Execution flow (`run_baseline`)

1. Structural agent validation (`validate_target_agent`); malformed agents
   raise `TypeError` before any environment work.
2. Budget gate: `budget.is_exhausted({"episodes": 0})` refuses the run with
   `ValueError` when `max_episodes=0`. One completed run consumes exactly
   one episode (`budget_usage == {"episodes": 1}`).
3. Environment constructed from `BaselineConfig.to_env_config()`; its
   `spec()` (including `market_fingerprint`) is snapshotted.
4. `agent.reset()` + `env.reset()` (lifecycle effects; the reset dict is
   discarded — observations flow only through `trusted.py`).
5. Per grid session: `observe_current(env)` → `invoke_act(agent, obs)` →
   `validate_orders` recorded with the env's universe → `env.step(orders)`
   → one immutable `DecisionRecord` from actuals. Malformed agent output
   aborts loudly with `TypeError`; no partial result is returned.
6. Pure metrics over the records, evidence derivation into the
   `baseline_evidence` slot, `NO_ACTIONABLE_FAILURE` stopping, and a frozen
   `BaselineResult` artefact.

## Trusted observation path (`trusted.py`)

E0 requires an `EnvironmentState` instance; public `reset()/step()` return
dicts. The adapter calls the environment's own `_state_at` at its current
grid index and wraps the instance via `from_environment_state` — no
reimplementation, no dict reconstruction, no environment modification.
Underscore access lives only here and is pinned by tests that fail loudly
on API drift.

## DecisionRecord semantics

One record per grid session: `state_fingerprint` = observation fingerprint;
visible/unavailable split from slot statuses; submitted orders deep-copied
then deep-frozen (agent-owned objects never retained); validation rows from
the env's own validator in env sort order; executions copied from env
`info`; `reward = info["step_pnl"]` with E0's exact `after − before`
equality enforced per record; `agent_metadata = None` (order-only
contract).

## Metrics (25, per-session grain, `None` with reason when unmeasurable)

Performance: `cumulative_return`, `volatility_per_session`,
`sharpe_per_session`, `sortino_per_session`, `max_drawdown` (env formula),
`worst_session_return`. Trading: `order_count`, `executed_notional`,
`turnover` (notional / mean equity), `transaction_cost_total`,
`concentration_cost_basis_max` (cost-basis: marks are not in records),
`position_persistence`, `reversal_rate`, `inactivity_rate`. Risk:
`gross_exposure_max/mean`, `net_exposure_max ≡ gross` and
`leverage_max ≡ gross` (long-only, unlevered identities by construction).
Validity: `invalid_order_count/rate`, `universe_violation_count`,
`no_price_count`, `calendar_gate_count`, `unavailable_info_session_count/rate`.

Not implemented, by design: annualised statistics (presentation only),
parametric VaR/CVaR (session grain cannot support tail estimation),
mark-to-market concentration (needs data outside the record),
regime-conditioned metrics (slot values are outside record scope —
E2 work). No metric carries a threshold or failure label.

## Evidence (11 items, derivation only)

`turnover`, `concentration_cost_basis_max`, `gross_exposure_max`,
`max_drawdown`, `position_persistence`, `inactivity_rate`, `reversal_rate`,
`invalid_order_rate`, `universe_violation_count`, `transaction_cost_total`,
`unavailable_info_rate` → categories RISK / DECISION_BEHAVIOR / EXECUTION /
INFORMATION_USAGE. Ids `E1-{evaluation_id}-{metric}`, methods
`e1.<metric>.v1`, refs = all contributing record fingerprints, undefined
metrics carried explicitly with reasons. TEMPORAL / MARKET_REGIME /
ROBUSTNESS unused (fixed session clock; no value-level regime inputs;
robustness needs interventions). Zero `Hypothesis` objects.

## Budget / stopping

`max_episodes=0` refuses pre-execution; otherwise one window = one episode.
Tests/repairs/validation_runs are unconsumed. `max_runtime` is recorded,
never wall-clock enforced (enforcement would inject nondeterminism).
Natural completion maps to E0 `NO_ACTIONABLE_FAILURE`: E1 raises nothing
actionable by design — a lifecycle mapping, NOT evidence the agent is
good. `HYPOTHESIS_UNRESOLVED` / `REPAIR_FAILED` / `REGRESSION_DETECTED`
are never emitted.

## Determinism

Same agent identity/version, environment fingerprint, config, and window
⇒ byte-identical artefact and fingerprint. No randomness is consumed
(`seed` is provenance-only); no wall-clock enters fingerprinted payloads.
Verified by double-run equality tests and identity-sensitivity tests.
