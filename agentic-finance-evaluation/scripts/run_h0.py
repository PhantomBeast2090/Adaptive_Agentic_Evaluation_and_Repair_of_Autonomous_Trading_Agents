"""H0 runner: same policy + same market window, varied initial capital.

For each pre-registered state (S0..S3, see configs/choice_agent/
h0_states.yaml): BaselineConfig differing ONLY in initial_cash,
frozen MultiAssetChoice (g1.yaml params), identical window
2020-01-01..2020-09-30 via run_baseline. Persists per-branch frozen
traces under data/frozen_traces/_h0/ plus a fingerprinted spec.
No attribution, no mining, no repair, no MemoryStore contact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

import yaml

sys.path.insert(0, ".")

from agents.choice.multi_asset import MultiAssetChoice
from evaluation.attribution.persistence import code_sha, sha256_of_file
from evaluation.baseline.config import BaselineConfig
from evaluation.baseline.runner import run_baseline
from evaluation.contracts.budget import EvaluationBudget
from scripts.run_g1 import build_config as _g1_build_config

SPEC_PATH = "configs/choice_agent/h0_states.yaml"
G1_POLICY = "configs/choice_agent/g1.yaml"

MANIFEST_PATHS = [
    "configs/indian_environment.yaml",
    "configs/choice_agent/g1.yaml",
    "configs/choice_agent/h0_states.yaml",
    "agents/choice/policy.py",
    "agents/choice/multi_asset.py",
    "data/processed/india/calendars/historical_calendar.csv",
    "data/processed/india/equities/nse_equity_daily.csv",
]


def _fingerprint(payload) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def load_spec(base_dir: str) -> dict:
    with open(os.path.join(base_dir, SPEC_PATH)) as h:
        return yaml.safe_load(h)


def build_config(experiment_id: str, start: str, end: str,
                 initial_cash: float) -> BaselineConfig:
    import dataclasses
    cfg = _g1_build_config(experiment_id, start, end)
    return dataclasses.replace(cfg, initial_cash=float(initial_cash))


def save_branch(base_dir: str, experiment_id: str, config: BaselineConfig,
                result_dict: dict, agent_params: dict, state: dict,
                overwrite: bool = False) -> str:
    out_dir = os.path.join(base_dir, "data", "frozen_traces", "_h0",
                           experiment_id)
    if os.path.exists(out_dir) and not overwrite:
        raise FileExistsError(
            f"refusing to overwrite existing H0 artefact dir {out_dir}")
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
        "state": dict(state),
        "intervention": "initial_cash only; policy/market identical",
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
    parser = argparse.ArgumentParser(description="Run H0 capital branches")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    base = args.base_dir
    spec = load_spec(base)
    window = spec["window"]
    with open(os.path.join(base, G1_POLICY)) as h:
        policy = yaml.safe_load(h)["policy"]
    outs = []
    for state in spec["states"]:
        exp_id = f"{args.experiment_id}-{state['id']}"
        config = build_config(exp_id, window["start"], window["end"],
                              state["initial_cash"])
        agent = MultiAssetChoice(policy)
        result = run_baseline(agent, config, base_dir=base)
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
        out = save_branch(base, exp_id, config, result_dict,
                          agent.params, state, args.overwrite)
        print(f"H0 {exp_id}: {len(result_dict['decision_records'])} "
              f"records -> {out}")
        print(f"  fingerprint: {result_dict['result_fingerprint']}")
        outs.append(out)
    spec_dir = os.path.join(base, "data", "frozen_traces", "_h0",
                            args.experiment_id)
    os.makedirs(spec_dir, exist_ok=True)
    with open(os.path.join(spec_dir, "spec.json"), "w",
              encoding="utf-8") as h:
        json.dump(spec, h, sort_keys=True, separators=(",", ":"))
        h.write("\n")
    print(f"H0 {args.experiment_id}: {len(outs)} branches complete")


if __name__ == "__main__":
    main()
