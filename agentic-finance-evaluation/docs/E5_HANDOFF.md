# E5 Attribution Layer Handoff

## 1. Summary of Completed Work (Milestone 1)
We have successfully implemented the infrastructure for the **E5 Deterministic Trajectory Attribution Layer**. 
This layer structurally enforces the boundary between Point-In-Time (PIT) decision data and evaluator-only retrospective data (e.g., forward returns).

### New Files Added:
- **`src/schemas/attribution.py`**: Defines the `AttributedDecision` schema which wraps the frozen raw `DecisionRecord`, splitting data strictly into `DecisionTimeState` and `AttributionOutcomes`.
- **`evaluation/attribution/engine.py`**: Contains the `DecisionAttributionEngine` responsible for joining traces with forward/trailing returns. The logic safely utilizes `environment.indian.clock` and `InformationLookup.bar_close()` to resolve exact market days, bypassing holidays securely.
- **`scripts/run_e5_attribution.py`**: A CLI orchestrator designed to ingest frozen E4-E JSON artefacts, verify trajectory fingerprints (stubbed, see below), and execute the attribution pipeline on the historical traces.
- **`tests/attribution/test_engine.py`**: A synthetic test suite validating the mechanical integrity of the PIT separation and engine structure.

## 2. Critical Reproducibility Discovery (Milestone E5-B)
During the transition to execute the attribution layer on real `E4-E` historical runs, a deep repository audit revealed a critical limitation:
**The original E4-E Parquet trajectories and MemoryStore context payloads are unrecoverable from this repository.**

1. `results/` and `logs/` (where the `TraceLogger` dumped parquet trajectories) are explicitly ignored in `.gitignore` and have never been committed to git.
2. The specific agent context payload (`ctx-dd5fd06281b18169`) referenced in the `E4E-turnover` experiment artifact is absent from git history, meaning we cannot synthetically re-run the agent to regenerate the traces.
3. The frozen E4-E artifact JSON contains only aggregated metrics (e.g. `order_count: 30`, `turnover: 0.88`) and hashes, lacking the required step-by-step decision states required for ML attribution.

## 3. Scientific Impact & Next Steps
- **Scientific Status**: The behavioral changes induced by the E4-E context injection are validated by aggregate metrics, but the absence of preserved trajectory records prevents retrospective decision-quality attribution (MAE, MFE, opportunity costs).
- **ML Blocked**: We cannot build ML datasets from this specific E4-E historical run because fabricating order-level fills from aggregate metrics would invalidate the research.
- **Immediate Requirement**: Future E0-E3 experiments must be governed by a mandatory **Trajectory Persistence Contract**, where `TraceLogger` artifacts and full `MemoryStore` payloads are persisted into a committed artifact registry (e.g., `data/frozen_traces/`), bypassing `.gitignore`.

*All implementation code has been committed to this branch, pending real trajectory data to perform full integration testing and MAE/MFE definition.*
