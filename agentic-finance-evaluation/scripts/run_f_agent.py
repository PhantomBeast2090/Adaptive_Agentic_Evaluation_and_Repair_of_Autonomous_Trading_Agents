"""F0 baseline runner: ChoiceAccumulator WITHOUT repair.

Runs the two pre-registered windows (F0-A crash-inclusive, F0-B E5A
comparability) through the frozen run_baseline interface and persists
baseline-only frozen traces (attribution is F1, not here). Fails
closed on existing artefact dirs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, ".")

from agents.choice.policy import ChoiceAccumulator
from evaluation.attribution.persistence import code_sha, sha256_of_file
from evaluation.baseline.config import BaselineConfig
from evaluation.baseline.runner import run_baseline
from evaluation.contracts.budget import EvaluationBudget

WINDOWS = {
    "F0-A": ("2019-11-01", "2020-05-29"),
    "F0-B": ("2023-05-15", "2023-08-14"),
}

MANIFEST_PATHS = [
    "configs/indian_environment.yaml",
    "configs/choice_agent/f0.yaml",
    "agents/choice/policy.py",
    "data/processed/india/calendars/historical_calendar.csv",
    "data/processed/india/equities/nse_equity_daily.csv",
]


def _fingerprint(payload) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_config(experiment_id: str, start: str, end: str) -> BaselineConfig:
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
        seed=None,
    )


def save_f0(base_dir: str, experiment_id: str, config: BaselineConfig,
            result_dict: dict, overwrite: bool = False) -> str:
    out_dir = os.path.join(base_dir, "data", "frozen_traces", experiment_id)
    if os.path.exists(out_dir) and not overwrite:
        raise FileExistsError(
            f"refusing to overwrite existing F0 artefact dir {out_dir}")
    os.makedirs(out_dir, exist_ok=True)

    def write(name: str, payload) -> None:
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as h:
            json.dump(payload, h, sort_keys=True, separators=(",", ":"))
            h.write("\n")

    write("baseline_config.json", config.to_dict())
    write("environment_spec.json", dict(result_dict["environment_spec"]))
    write("baseline_result.json", {
        k: v for k, v in result_dict.items() if k != "environment_spec"
        and k != "config"})
    manifest = {
        "experiment_id": experiment_id,
        "agent": dict(result_dict["agent_identity"]),
        "result_fingerprint": result_dict["result_fingerprint"],
        "code_sha": code_sha(base_dir),
        "data_shas": {p: sha256_of_file(os.path.join(base_dir, p))
                      for p in MANIFEST_PATHS},
        "config_fingerprint": _fingerprint(config.to_dict()),
    }
    manifest["manifest_fingerprint"] = _fingerprint(
        {k: v for k, v in manifest.items()
         if k != "manifest_fingerprint"})
    write("manifest.json", manifest)
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Run F0 baselines")
    parser.add_argument("--window", choices=sorted(WINDOWS), required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    start, end = WINDOWS[args.window]
    config = build_config(args.experiment_id, start, end)
    agent = ChoiceAccumulator()
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
    out = save_f0(args.base_dir, args.experiment_id, config, result_dict,
                  args.overwrite)
    n = len(result_dict["decision_records"])
    print(f"F0 {args.experiment_id} ({args.window}): {n} records -> {out}")
    print(f"result fingerprint: {result_dict['result_fingerprint']}")


if __name__ == "__main__":
    main()
