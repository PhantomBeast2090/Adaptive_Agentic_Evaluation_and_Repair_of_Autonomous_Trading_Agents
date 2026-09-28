"""F1 attribution: frozen E5A engine over F0R baseline traces.

No new evaluator. Reads each F0R-* baseline_result.json, resolves the
frozen session grid from its environment spec, runs
DecisionAttributionEngine.attribute_trajectory read-only, and persists
via save_experiment under a new F1R-* id. PIT + exact-bar semantics
identical to E5A.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys

sys.path.insert(0, ".")

from environment.indian.clock import build_master_grid, load_default_resolver
from evaluation.attribution.engine import DecisionAttributionEngine
from evaluation.attribution.persistence import REGISTRY_ROOT, save_experiment


class CachedAttributionEngine(DecisionAttributionEngine):
    """Performance shim: identical _ohlc semantics, cached CSV frames.

    The frozen engine re-reads the full CSV per leg; this override
    loads each spec CSV once and applies the byte-identical filter
    logic. Equivalence is proven by re-attributing F1R-B both ways
    and comparing fingerprints (see F1 audit). Frozen engine file
    untouched.
    """

    def __init__(self, base_dir: str = "."):
        super().__init__(base_dir=base_dir)
        self._ohlc_frames = {}

    def _ohlc(self, asset_id, instrument, session):
        import os

        import pandas as pd

        from environment.indian.registry import get_spec
        from evaluation.attribution.engine import instrument_filter

        try:
            spec = get_spec(asset_id)
            filt = instrument_filter(asset_id, instrument) or {}
            use = [spec.observation_col, "open", "high", "low", "close"]
            use += list(filt.keys())
            use = list(dict.fromkeys(use))
            key = spec.csv_path
            if key not in self._ohlc_frames:
                path = os.path.join(self.base_dir, spec.csv_path)
                frame = pd.read_csv(path, usecols=lambda c: c in set(use))
                frame = frame.copy()
                frame["_obs"] = pd.to_datetime(
                    frame[spec.observation_col], errors="coerce")
                frame = frame.dropna(subset=["_obs"])
                self._ohlc_frames[key] = (frame, spec.observation_col)
            frame, obs_col = self._ohlc_frames[key]
            sub = frame
            for col, val in filt.items():
                sub = sub[sub[col].astype(str) == str(val)]
            hits = sub[sub["_obs"].dt.date.astype(str) == session]
            if hits.empty:
                return None
            row = hits.iloc[-1]
            out = {}
            for col in ("open", "high", "low", "close"):
                if col in row:
                    try:
                        val = float(row[col])
                    except (TypeError, ValueError):
                        continue
                    if val == val and val > 0:
                        out[col] = val
            if "high" not in out or "low" not in out:
                return None
            return out
        except Exception:
            return None

F0_MAP = {
    "F0R-A-20260926": "F1R-A-20260926",
    "F0R-B-20260926": "F1R-B-20260926",
    "F3-A-20260926": "F3A-20260926",
    "F3-B-20260926": "F3B-20260926",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run F1 attribution")
    parser.add_argument("--f0-id", choices=sorted(F0_MAP), required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--arm", default="A")
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    assert args.experiment_id.startswith(("F1R-", "F3")), \
        "attribution ids live under the F1R-/F3 namespaces"

    src = os.path.join(base_dir := args.base_dir, "data", "frozen_traces",
                       args.f0_id)
    with open(os.path.join(src, "baseline_result.json")) as h:
        result_dict = json.load(h)
    with open(os.path.join(src, "baseline_config.json")) as h:
        config_dict = json.load(h)
    with open(os.path.join(src, "environment_spec.json")) as h:
        env_spec = json.load(h)

    grid = [d.isoformat() for d in build_master_grid(
        load_default_resolver(base_dir),
        _dt.date.fromisoformat(env_spec["grid_start"]),
        _dt.date.fromisoformat(env_spec["grid_end"]))]
    episode_id = args.experiment_id + "-ep1"
    engine = CachedAttributionEngine(base_dir=base_dir)
    attribution = engine.attribute_trajectory(
        decision_records=result_dict["decision_records"],
        episode_id=episode_id,
        arm=args.arm,
        trajectory_fingerprint=result_dict["result_fingerprint"],
        run_id=args.experiment_id + "-run-001",
        experiment_id=args.experiment_id,
        experiment_grid=grid,
        context_descriptor="C0-empty-store",
    )
    attribution_dict = attribution.to_dict()
    extra = {"attribution_fingerprint": attribution.fingerprint(),
             "arm": args.arm, "registry": REGISTRY_ROOT,
             "source_experiment": args.f0_id}
    policy_cfg = ("configs/choice_agent/f3.yaml"
                  if args.experiment_id.startswith("F3")
                  else "configs/choice_agent/f0r.yaml")
    out = save_experiment(
        base_dir=base_dir, experiment_id=args.experiment_id,
        config_dict=config_dict, environment_spec=env_spec,
        baseline_result_dict=result_dict,
        attribution_dict=attribution_dict,
        manifest_paths=[
            "configs/indian_environment.yaml",
            policy_cfg,
            "agents/choice/policy.py",
            "data/processed/india/calendars/historical_calendar.csv",
            "data/processed/india/equities/nse_equity_daily.csv",
            "data/processed/india/instruments/mcx_gold_futures_individual_contracts.csv",
        ],
        extra=extra, overwrite=args.overwrite)
    n = len(attribution_dict.get("attributed_decisions", []))
    print(f"F1 {args.experiment_id}: {n} rows -> {out}")
    print(f"attribution fingerprint: {extra['attribution_fingerprint']}")


if __name__ == "__main__":
    main()
