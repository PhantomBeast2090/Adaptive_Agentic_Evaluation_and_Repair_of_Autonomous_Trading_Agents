"""G1 runner: multi-asset baselines for G1-A/G1-B via run_baseline.

Mirrors scripts/run_f_agent.py with the G1 universe/policy config.
Persists baseline-only frozen traces (attribution/mining only if the
support gate passes). Fails closed on existing artefact dirs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

import yaml

sys.path.insert(0, ".")

from agents.choice.multi_asset import G1_INSTRUMENTS, MultiAssetChoice
from evaluation.attribution.persistence import code_sha, sha256_of_file
from evaluation.baseline.config import BaselineConfig
from evaluation.baseline.runner import run_baseline
from evaluation.contracts.budget import EvaluationBudget

WINDOWS = {
    "G1-A": ("2020-01-01", "2020-09-30"),
    "G1-B": ("2020-10-01", "2021-03-31"),
}
POLICY_CONFIG = "configs/choice_agent/g1.yaml"

MANIFEST_PATHS = [
    "configs/indian_environment.yaml",
    "configs/choice_agent/g1.yaml",
    "agents/choice/policy.py",
    "agents/choice/multi_asset.py",
    "data/processed/india/calendars/historical_calendar.csv",
    "data/processed/india/equities/nse_equity_daily.csv",
    "data/frozen_traces/_g1/universe.json",
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
            "nse_equity": [i.split(":")[0] + ":EQ" for i in G1_INSTRUMENTS],
            "mcx_gold": ["GOLDAUG2023"],
        },
        transaction_cost_bps=5.0,
        initial_cash=100000.0,
        strict_pit=True,
        vintage_policy="explicit",
        budget=EvaluationBudget(
            max_episodes=10, max_tests=None, max_repairs=None,
            max_validation_runs=None, max_runtime=None),
        seed=None,
    )


def save_g1(base_dir: str, experiment_id: str, config: BaselineConfig,
            result_dict: dict, agent_params: dict,
            overwrite: bool = False) -> str:
    out_dir = os.path.join(base_dir, "data", "frozen_traces", experiment_id)
    if os.path.exists(out_dir) and not overwrite:
        raise FileExistsError(
            f"refusing to overwrite existing artefact dir {out_dir}")
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
        "agent_params": dict(agent_params),
        "policy_config": POLICY_CONFIG,
        "result_fingerprint": result_dict["result_fingerprint"],
        "code_sha": code_sha(base_dir),
        "data_shas": {p: sha256_of_file(os.path.join(base_dir, p))
                      for p in MANIFEST_PATHS},
        "config_fingerprint": _fingerprint(config.to_dict()),
    }
    manifest["manifest_fingerprint"] = _fingerprint(
        {k: v for k, v in manifest.items() if k != "manifest_fingerprint"})
    write("manifest.json", manifest)
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Run G1 baselines")
    parser.add_argument("--window", choices=sorted(WINDOWS), required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    with open(os.path.join(args.base_dir, POLICY_CONFIG)) as h:
        policy = yaml.safe_load(h)["policy"]
    from agents.choice.policy import DEFAULTS, V11_DEFAULTS
    from agents.choice.multi_asset import G1_DEFAULTS
    allowed = (set(DEFAULTS) | set(V11_DEFAULTS) | set(G1_DEFAULTS)
               | {"vix_slot", "instruments"})
    unknown = set(policy) - allowed
    if unknown:
        raise ValueError(f"policy config keys not in agent table: {unknown}")
    start, end = WINDOWS[args.window]
    config = build_config(args.experiment_id, start, end)
    agent = MultiAssetChoice(policy)
    result = run_baseline(agent, config, base_dir=args.base_dir)
    result_dict = {
        "evaluation_id": result.evaluation_id,
        "agent_identity": {"agent_id": result.agent_identity.agent_id,
                           "version": result.agent_identity.version},
        "environment_spec": dict(result.environment_spec),
        "config": result.config.to_dict(),
        "decision_records": [r.to_dict() for r in result.decision_records],
        "metrics": [m.to_dict() for m in result.metrics],
        "budget_usage": dict(result.budget_usage),
        "result_fingerprint": result.fingerprint(),
    }
    out = save_g1(args.base_dir, args.experiment_id, config, result_dict,
                  agent.params, args.overwrite)
    print(f"G1 {args.experiment_id} ({args.window}): "
          f"{len(result_dict['decision_records'])} records -> {out}")
    print(f"result fingerprint: {result_dict['result_fingerprint']}")


if __name__ == "__main__":
    main()
