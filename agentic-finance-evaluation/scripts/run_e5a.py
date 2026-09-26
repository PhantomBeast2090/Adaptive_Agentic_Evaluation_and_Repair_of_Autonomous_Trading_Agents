"""E5a deterministic attribution experiment (NEW evidence, not E4-E recovery).

Pipeline:
  BaselineConfig -> run_baseline (canonical runner) -> BaselineResult
  -> DecisionAttributionEngine (PIT-safe joins) -> DecisionAttributionResult
  -> data/frozen_traces/<experiment_id>/ (tracked persistence contract)

Usage:
  python scripts/run_e5a.py --experiment-id E5A-deterministic-attribution-YYYYMMDD \\
      --start 2023-05-15 --end 2023-06-15 --arm A

Historical note: scripts/run_e5_attribution.py remains untouched as the
frozen E4-E-coupled stub. This script is the new-experiment path.
"""

from __future__ import annotations

import argparse
import sys

sys.path.insert(0, ".")

from benchmarks.volatility_threshold import VolatilityThresholdBenchmark
from evaluation.attribution.engine import DecisionAttributionEngine
from evaluation.attribution.persistence import REGISTRY_ROOT, save_experiment
from evaluation.baseline.config import BaselineConfig
from evaluation.baseline.runner import run_baseline
from evaluation.contracts.budget import EvaluationBudget


def build_config(
    experiment_id: str, start: str, end: str, seed: int | None = None
) -> BaselineConfig:
    return BaselineConfig(
        evaluation_id=experiment_id,
        start_date=start,
        end_date=end,
        universe={
            "nse_equity": ["RELIANCE:EQ", "TCS:EQ", "INFY:EQ"],
            "mcx_gold": ["GOLDAUG2023"],
        },
        transaction_cost_bps=5.0,
        initial_cash=100000.0,
        strict_pit=True,
        vintage_policy="explicit",
        budget=EvaluationBudget(
            max_episodes=10,
            max_tests=None,
            max_repairs=None,
            max_validation_runs=None,
            max_runtime=None,
        ),
        seed=seed,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run NEW E5a attribution experiment")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--start", default="2023-05-15")
    parser.add_argument("--end", default="2023-06-15")
    parser.add_argument("--arm", default="A")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    config = build_config(args.experiment_id, args.start, args.end, args.seed)
    agent = VolatilityThresholdBenchmark()
    result = run_baseline(agent, config, base_dir=args.base_dir)
    result_dict = {
        "evaluation_id": result.evaluation_id,
        "agent_identity": {
            "agent_id": result.agent_identity.agent_id,
            "version": result.agent_identity.version,
        },
        "environment_spec": dict(result.environment_spec),
        "config": result.config.to_dict(),
        "decision_records": [r.to_dict() for r in result.decision_records],
        "metrics": [m.to_dict() for m in result.metrics],
        "budget_usage": dict(result.budget_usage),
        "result_fingerprint": result.fingerprint(),
    }
    trajectory_fp = result.fingerprint()
    # Rebuild the experiment grid deterministically from the recorded spec.
    import datetime as _dt

    start_d = _dt.date.fromisoformat(result.environment_spec["grid_start"])
    end_d = _dt.date.fromisoformat(result.environment_spec["grid_end"])
    from environment.indian.clock import build_master_grid, load_default_resolver

    grid = [
        d.isoformat()
        for d in build_master_grid(
            load_default_resolver(args.base_dir), start_d, end_d
        )
    ]
    episode_id = args.experiment_id + "-ep1"

    engine = DecisionAttributionEngine(base_dir=args.base_dir)
    attribution = engine.attribute_trajectory(
        decision_records=list(result.decision_records),
        episode_id=episode_id,
        arm=args.arm,
        trajectory_fingerprint=trajectory_fp,
        run_id=args.experiment_id + "-run-001",
        experiment_id=args.experiment_id,
        experiment_grid=grid,
        context_descriptor="C0-empty-store",
    )
    attribution_dict = attribution.to_dict()
    extra = {
        "attribution_fingerprint": attribution.fingerprint(),
        "arm": args.arm,
        "registry": REGISTRY_ROOT,
    }
    out = save_experiment(
        base_dir=args.base_dir,
        experiment_id=args.experiment_id,
        config_dict=config.to_dict(),
        environment_spec=dict(result.environment_spec),
        baseline_result_dict=result_dict,
        attribution_dict=attribution_dict,
        manifest_paths=[
            "configs/indian_environment.yaml",
            "data/processed/india/calendars/historical_calendar.csv",
            "data/processed/india/equities/nse_equity_daily.csv",
            "data/processed/india/instruments/mcx_gold_futures_individual_contracts.csv",
        ],
        extra=extra,
        overwrite=args.overwrite,
    )
    n_rows = len(attribution_dict.get("attributed_decisions", []))
    print(f"E5a experiment {args.experiment_id}: {n_rows} rows -> {out}")
    print(f"attribution fingerprint: {extra['attribution_fingerprint']}")


if __name__ == "__main__":
    main()
