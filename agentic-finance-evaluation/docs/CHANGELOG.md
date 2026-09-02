
## Initial Setup
- Project repository initialized
- Dataset acquisition performed
- Dataset metadata created
- Initial schemas created
- Development infrastructure prepared

## Current MVP Evaluation Loop
- Added concordance gate between deterministic discovery and blinded diagnosis.
- Added deterministic intervention generation for concordant vulnerabilities.
- Added deterministic repair re-evaluation with side-effect and holdout checks.
- Configured pytest to collect only project-owned tests.

## Phase 1 Audit and Freeze
- Stabilized environment observations for direct agent consumption.
- Added agent reset semantics for episode-local state.
- Hardened portfolio accounting against impossible negative trades.
- Added market-data validation for processed replay inputs.
- Added deterministic end-to-end episode and edge-case tests.
- Documented the Phase 1 environment contract and information boundary.

## Phase 1.5 Environment Contract Freeze
- Defined final-row execution semantics: one action per market row, including
  the final row.
- Returned final observable portfolio state on terminal transitions.
- Added execution price, portfolio value, cash, and holdings to step outcomes.
- Documented partial-fill, invalid-action, termination, reward, cost, and
  information-boundary semantics.
- Added regression tests for final timestep accounting, deterministic replay,
  trajectory completeness, look-ahead protection, and portfolio invariants.
