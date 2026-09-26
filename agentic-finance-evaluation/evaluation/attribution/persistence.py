"""E5a persistence contract.

Every E5a experiment persists the full decision-level evidence needed to
re-attribute it later (the E4-E loss must never repeat):

  * BaselineConfig + environment spec + code SHA + data manifest SHAs
  * full BaselineResult dict (including every DecisionRecord)
  * full DecisionAttributionResult dict + flat CSV decision table

Artefacts live under a tracked registry path (``data/frozen_traces/``),
never under git-ignored ``results/`` or ``logs/``. Writes are
fail-closed: an existing artefact directory is never silently
overwritten (pass overwrite=True explicitly for a deliberate rerun,
which records the rerun in manifest.json).
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
from typing import Any, Dict, List, Mapping

REGISTRY_ROOT = os.path.join("data", "frozen_traces")


def code_sha(base_dir: str = ".") -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=15,
        )
        sha = out.stdout.strip()
        if sha:
            return sha
    except Exception:
        pass
    return "UNKNOWN"


def sha256_of_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: str, payload: Mapping[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")


def flatten_attribution(result_dict: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Project the nested attribution result to one flat row per decision."""
    rows: List[Dict[str, Any]] = []
    for item in result_dict.get("attributed_decisions", []):
        state = item.get("decision_time_state", {}) or {}
        outcomes = item.get("outcomes", {}) or {}
        before = state.get("portfolio_before", {}) or {}
        after = state.get("portfolio_after", {}) or {}
        prov = item.get("provenance", {}) or {}
        snap = (state.get("market_features", {}) or {}).get("pit_snapshot", {}) or {}
        rows.append(
            {
                "experiment_id": result_dict.get("experiment_id"),
                "episode_id": item.get("episode_id"),
                "decision_id": item.get("decision_id"),
                "arm": item.get("arm"),
                "decision_timestamp": state.get("decision_timestamp"),
                "instrument": state.get("instrument"),
                "action": state.get("action"),
                "quantity": state.get("quantity"),
                "execution_price": state.get("execution_price"),
                "cash_before": before.get("cash"),
                "total_equity_before": before.get("total_equity"),
                "exposure_before": before.get("exposure"),
                "cash_after": after.get("cash"),
                "total_equity_after": after.get("total_equity"),
                "reward": (
                    (after.get("total_equity") - before.get("total_equity"))
                    if isinstance(after.get("total_equity"), (int, float))
                    and isinstance(before.get("total_equity"), (int, float))
                    else None
                ),
                "agent_context_version": state.get("agent_context_version"),
                "state_fingerprint": state.get("state_fingerprint"),
                "market_fingerprint": (state.get("market_features", {}) or {}).get(
                    "market_fingerprint"
                ),
                "pit_status": snap.get("status"),
                "pit_observation_date": snap.get("observation_date"),
                "pre_trend_1d": outcomes.get("pre_trend_1d"),
                "pre_trend_3d": outcomes.get("pre_trend_3d"),
                "pre_trend_5d": outcomes.get("pre_trend_5d"),
                "forward_return_1d": outcomes.get("forward_return_1d"),
                "forward_return_3d": outcomes.get("forward_return_3d"),
                "mae": outcomes.get("mae"),
                "mfe": outcomes.get("mfe"),
                "hold_return": outcomes.get("hold_return"),
                "opportunity_return": outcomes.get("opportunity_return"),
                "participation_status": item.get("participation_status"),
                "attribution_status": item.get("attribution_status"),
                "provenance_classification": prov.get("classification"),
            }
        )
    return rows


def save_experiment(
    base_dir: str,
    experiment_id: str,
    config_dict: Mapping[str, Any],
    environment_spec: Mapping[str, Any],
    baseline_result_dict: Mapping[str, Any],
    attribution_dict: Mapping[str, Any],
    manifest_paths: List[str],
    extra: Mapping[str, Any],
    overwrite: bool = False,
) -> str:
    """Persist one E5a experiment; return the artefact directory."""
    out_dir = os.path.join(base_dir, REGISTRY_ROOT, experiment_id)
    if os.path.exists(out_dir) and not overwrite:
        raise FileExistsError(
            f"refusing to overwrite existing E5a artefact dir {out_dir}; "
            "pass overwrite=True for a deliberate rerun"
        )
    os.makedirs(out_dir, exist_ok=True)

    _write_json(os.path.join(out_dir, "baseline_config.json"), dict(config_dict))
    _write_json(os.path.join(out_dir, "environment_spec.json"), dict(environment_spec))
    _write_json(
        os.path.join(out_dir, "baseline_result.json"), dict(baseline_result_dict)
    )
    _write_json(
        os.path.join(out_dir, "attribution.json"), dict(attribution_dict)
    )

    rows = flatten_attribution(attribution_dict)
    csv_path = os.path.join(out_dir, "decision_table.csv")
    if rows:
        with open(csv_path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    else:
        with open(csv_path, "w", encoding="utf-8", newline="") as handle:
            handle.write("")

    manifest: Dict[str, Any] = {
        "experiment_id": experiment_id,
        "code_sha": code_sha(base_dir),
        "data_manifests": {},
        "extra": dict(extra),
        "rerun": bool(overwrite),
    }
    for rel in manifest_paths:
        full = os.path.join(base_dir, rel)
        if os.path.exists(full):
            manifest["data_manifests"][rel] = sha256_of_file(full)
        else:
            manifest["data_manifests"][rel] = "MISSING"
    _write_json(os.path.join(out_dir, "manifest.json"), manifest)
    return out_dir
