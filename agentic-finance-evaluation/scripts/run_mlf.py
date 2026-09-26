"""ML-foundation runner: M3 classical cell + foundation forecast runs.

Usage:
  python scripts/run_mlf.py --experiment-id MLF-20260926 [--overwrite]
      [--models chronos2,timesfm3] [--smoke] [--skip-tabular]

Pipeline per foundation model (sequential, released between runs):
  E5A decisions -> PIT context (<T) -> zero-shot forecast
  -> normalised ForecastOutput -> derived diagnostic features
  -> diagnostic table (forecast x V1/V2 x evaluator outcomes)
  -> predictive cells (logistic head on forecast features, both targets)
  -> conditional miner (TRAIN/VALID) -> hypotheses -> validation review
  -> _ml_foundation persistence.

M3 (V2 x HistGradientBoosting, both targets) persists under _m2 for
direct comparability with M1/M2b. Nothing writes to MemoryStore; the
agent, runner, and validation machinery are untouched.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
from typing import Any

sys.path.insert(0, ".")

from evaluation.attribution import features_v2 as F2
from evaluation.ml import evaluation as metrics
from evaluation.ml.diagnosis import conditional_miner as CM
from evaluation.ml.diagnosis import forecast_diagnostics as FD
from evaluation.ml.diagnosis import hypothesis_builder as HB
from evaluation.ml.experiment import (
    PRIMARY_TARGET, SECONDARY_TARGET, TRAIN_WINDOW, TEST_WINDOW,
    VALID_WINDOW, run_cell,
)
from evaluation.ml.forecasting import forecast_features as FF
from evaluation.ml.forecasting.feature_adapter import build_context
from evaluation.ml.models import registry as REG
from evaluation.ml.models.hist_gradient_boosting import HGBModel
from evaluation.ml.models.logistic import LogisticModel
from evaluation.ml.models.timeseries_base import ModelStatus, ModelUnavailable
from evaluation.ml.persistence import (
    fingerprint_artefacts, save_foundation, save_m2, sha256_of_file,
)
from evaluation.ml.validation.ml_validation import validate_candidate

V1_DATASET = "data/frozen_traces/_ml/e5a_combined_v1.json"
V2_DATASET = "data/frozen_traces/_ml/e5a_combined_v2.json"
WINDOWS = {"train": TRAIN_WINDOW, "valid": VALID_WINDOW, "test": TEST_WINDOW}


def code_sha(base_dir: str) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=base_dir,
                             capture_output=True, text=True, timeout=15)
        return out.stdout.strip() or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def rss_mb() -> int:
    return resource.getrusage(
        resource.RUSAGE_SELF).ru_maxrss // 1048576


def package_versions(packages: list) -> dict:
    import importlib.metadata as md
    out = {}
    for p in packages:
        try:
            out[p] = md.version(p)
        except Exception:
            out[p] = "unavailable"
    return out


def load_model(model_id: str):
    if model_id == "chronos2":
        from evaluation.ml.models.chronos2 import Chronos2Model
        return Chronos2Model()
    if model_id == "timesfm3":
        from evaluation.ml.models.timesfm3 import TimesFM3Model
        return TimesFM3Model()
    raise ValueError(f"unknown foundation model {model_id}")


def run_forecasts(model_id: str, decisions: list, base_dir: str,
                  smoke: bool = False) -> dict:
    """Forecast every decision; per-decision BLOCKED rows preserve gaps."""
    model = load_model(model_id)
    try:
        outputs, derived = [], {}
        targets = decisions[:3] if smoke else decisions
        for i, row in enumerate(targets):
            keys = row["keys"]
            did = keys["decision_id"]
            instrument = str(row["features"].get("instrument")
                             or "UNKNOWN")
            try:
                ctx = build_context(
                    instrument, keys["decision_timestamp"],
                    base_dir=base_dir)
            except ValueError as exc:  # short history: gap preserved
                out = _blocked_output(
                    model_id,
                    {"decision_id": did, "instrument": instrument,
                     "decision_timestamp": keys["decision_timestamp"],
                     "context_fingerprint": "insufficient-history"},
                    ModelStatus.UNAVAILABLE, str(exc))
                outputs.append(out.to_dict())
                derived[did] = FF.derive(out)
                continue
            ctx = dict(ctx, decision_id=did,
                       instrument=instrument,
                       decision_timestamp=keys["decision_timestamp"])
            try:
                out = model.forecast(ctx)
            except ModelUnavailable as exc:
                status = exc.args[0] if exc.args else ModelStatus.UNAVAILABLE
                out = _blocked_output(model_id, ctx, status, str(exc))
            outputs.append(out.to_dict())
            derived[did] = FF.derive(out)
            if (i + 1) % 25 == 0:
                print(f"  {model_id}: {i + 1}/{len(targets)} "
                      f"(RSS {rss_mb()} MB)", flush=True)
        meta = model.metadata()
    finally:
        model.release()
    return {"outputs": outputs, "derived": derived, "metadata": meta}


def _blocked_output(model_id: str, ctx: dict, status: str,
                    reason: str) -> Any:
    from evaluation.ml.forecasting.base import ForecastOutput
    return ForecastOutput(
        model_id=model_id, model_version="unavailable",
        checkpoint_revision="unresolved",
        decision_id=str(ctx.get("decision_id", "")),
        instrument=str(ctx.get("instrument", "")),
        decision_timestamp=str(ctx.get("decision_timestamp", "")),
        context_fingerprint=str(ctx.get("context_fingerprint", "missing")),
        horizons=(1, 3, 5), quantiles=(0.1, 0.5, 0.9),
        quantile_paths=tuple(tuple([None] * 5) for _ in range(3)),
        reference_level=None, deterministic_seed=None,
        status=status, failure_reason=reason)


def split_by_window(rows: list) -> dict:
    out = {"train": [], "valid": [], "test": []}
    for r in rows:
        wid = r["keys"]["experiment_id"]
        if wid == TRAIN_WINDOW:
            out["train"].append(r)
        elif wid == VALID_WINDOW:
            out["valid"].append(r)
        elif wid == TEST_WINDOW:
            out["test"].append(r)
    return out


def predictive_dataset(diag_rows: list, numeric: list,
                       target: str) -> tuple:
    """Project the diagnostic table onto a run_cell-compatible dataset."""
    kept = [c for c in numeric if any(
        r["features"].get(c) is not None for r in diag_rows
        if r["keys"]["experiment_id"] == TRAIN_WINDOW)]
    ds_rows = []
    for r in diag_rows:
        ds_rows.append({
            "keys": dict(r["keys"]),
            "features": {c: r["features"].get(c) for c in kept},
            "outcomes": {target: r["outcome"]},
        })
    return {"rows": ds_rows}, kept


def directional_stats(diag_rows: list, v1_by_id: dict) -> dict:
    agree = n = 0
    for r in diag_rows:
        fwd = (v1_by_id.get(r["keys"]["decision_id"], {})
               .get("outcomes", {}).get("forward_return_3d"))
        f = r["features"].get("f_ret_3d")
        if fwd is None or f is None:
            continue
        n += 1
        if (f > 0) == (fwd > 0):
            agree += 1
    return {"n": n, "agreement": (agree / n) if n else None}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ML-foundation track")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--models", default="chronos2,timesfm3")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--skip-tabular", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    base = args.base_dir
    sha = code_sha(base)

    with open(os.path.join(base, V1_DATASET)) as h:
        v1 = json.load(h)
    with open(os.path.join(base, V2_DATASET)) as h:
        v2 = json.load(h)
    data_shas = {V1_DATASET: sha256_of_file(os.path.join(base, V1_DATASET)),
                 V2_DATASET: sha256_of_file(os.path.join(base, V2_DATASET))}

    # --- M3 classical cells (persist under _m2 for comparability) ---
    if not args.skip_tabular:
        from evaluation.attribution.features_v2 import (
            CATEGORICAL_FEATURES_V2, NUMERIC_FEATURES_V2,
            ZERO_FILL_FEATURES_V2,
        )
        for target in (PRIMARY_TARGET, SECONDARY_TARGET):
            art = run_cell(
                v2, f"M3-{target}", "V2", list(NUMERIC_FEATURES_V2),
                list(CATEGORICAL_FEATURES_V2),
                list(ZERO_FILL_FEATURES_V2),
                lambda names: HGBModel(names), target=target)
            out = save_m2(base, f"{args.experiment_id}-M3-{target}", art,
                          sha, data_shas[V2_DATASET], args.overwrite)
            print(f"M3-{target}: VALID Brier "
                  f"B0={art['b0']['valid']['brier']:.4f} "
                  f"M={art['model']['valid']['brier']:.4f} | TEST "
                  f"B0={art['b0']['test']['brier']:.4f} "
                  f"M={art['model']['test']['brier']:.4f} -> {out}")
            print(f"  fingerprint: {art['fingerprint']}")

    # --- Foundation runs ---
    for model_id in [m for m in args.models.split(",") if m.strip()]:
        status, reason, _ = REG.status_of(model_id)
        run_tag = f"{args.experiment_id}-{model_id}"
        if status != ModelStatus.AVAILABLE:
            art = {"status": status,
                   "blocker": {"reason": reason,
                               "registry": REG.describe()}}
            prov = _provenance(base, sha, data_shas, model_id,
                               {"status": status}, None)
            out = save_foundation(base, run_tag, art, prov,
                                  {"rss_mb": rss_mb()},
                                  args.overwrite)
            print(f"{run_tag}: {status} ({reason[:120]}) -> {out}")
            continue
        print(f"{run_tag}: forecasting {len(v1['rows'])} decisions...")
        res = run_forecasts(model_id, v1["rows"], base, smoke=args.smoke)
        v1_by_id = {r["keys"]["decision_id"]: r for r in v1["rows"]}

        per_target = {}
        for target in (PRIMARY_TARGET, SECONDARY_TARGET):
            table = FD.build_diagnostic_table(
                v1["rows"], v2["rows"], res["derived"], target=target)
            splits = split_by_window(table["rows"])
            ds, kept = predictive_dataset(
                table["rows"], list(FF.FORECAST_DERIVED_FEATURES), target)
            try:
                cell = run_cell(
                    ds, f"{model_id}-{target}", "F1", kept, [],
                    [], lambda names: LogisticModel(names), target=target)
            except (ValueError, ModelUnavailable) as exc:
                cell = {"status": "BLOCKED",
                        "blocker": str(exc)[:300]}
            per_target[target] = {
                "table": table, "splits": splits, "cell": cell,
                "kept": kept}
        primary = per_target[PRIMARY_TARGET]
        table, splits = primary["table"], primary["splits"]
        cells = {t: per_target[t]["cell"]
                 for t in (PRIMARY_TARGET, SECONDARY_TARGET)}

        mined = CM.mine(splits["train"], splits["valid"], splits["test"],
                        target=PRIMARY_TARGET)
        HB.set_band_cache(mined["spec"])
        hypotheses, validations = [], []
        forecast_fp = fingerprint_artefacts(
            {"outputs": res["outputs"]})
        info_fp = fingerprint_artefacts({"data_shas": data_shas})
        for j, cand in enumerate(mined["candidates"]):
            dh = HB.from_condition(
                cand, splits["train"],
                [TRAIN_WINDOW, VALID_WINDOW, TEST_WINDOW],
                res["metadata"], forecast_fp,
                info_fp,
                PRIMARY_TARGET, f"{run_tag}-H{j + 1}")
            hypotheses.append(dh.to_dict())
            validations.append(validate_candidate(dh.to_dict()))

        art = {
            "config": {"run_id": run_tag, "model_id": model_id,
                       "targets": [PRIMARY_TARGET, SECONDARY_TARGET],
                       "smoke": args.smoke,
                       "forecaster_metadata": res["metadata"]},
            "forecast_outputs": res["outputs"],
            "diagnostic_table": [
                {"decision_id": r["keys"]["decision_id"],
                 "experiment_id": r["keys"]["experiment_id"],
                 "features": r["features"],
                 "feature_provenance": r["feature_provenance"],
                 "outcome": r["outcome"]} for r in table["rows"]],
            "predictive_cells": {
                t: {k: c.get(k) for k in (
                    "status", "fingerprint", "b0", "model",
                    "permutation", "missingness_only")}
                for t, c in cells.items()},
            "mined_conditions": mined,
            "hypotheses": hypotheses,
            "validations": validations,
            "forecast_utility": directional_stats(table["rows"], v1_by_id),
        }
        prov = _provenance(base, sha, data_shas, model_id, res["metadata"],
                           forecast_fp)
        out = save_foundation(base, run_tag, art, prov,
                              {"rss_mb": rss_mb()},
                              args.overwrite)
        print(f"{run_tag}: complete -> {out}")
        print(f"  manifest fingerprint: "
              f"{json.load(open(os.path.join(out, 'manifest.json'))).get('fingerprint')}")


def _provenance(base: str, sha: str, data_shas: dict, model_id: str,
                model_meta: Any, forecast_fp: Any) -> dict:
    return {
        "code_sha": sha,
        "data_shas": data_shas,
        "model_id": model_id,
        "model_metadata": model_meta,
        "forecast_fingerprint": forecast_fp,
        "dependency_versions": package_versions(
            ["scikit-learn", "torch", "numpy", "pandas",
             "chronos-forecasting", "timesfm", "huggingface_hub"]),
        "device": "cpu",
        "seed": 20260926,
        "config": {"horizons": [1, 3, 5], "quantiles": [0.1, 0.5, 0.9],
                   "context_length": 256, "univariate": True,
                   "zero_shot": True},
        "windows": WINDOWS,
    }


if __name__ == "__main__":
    main()
