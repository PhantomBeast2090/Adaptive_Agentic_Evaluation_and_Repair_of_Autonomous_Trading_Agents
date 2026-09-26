"""Canonical ML feature-generation layer for E5a attribution data.

Architecture (no manual JSON assembly at model time):

  persisted trajectory (BaselineResult + DecisionAttributionResult)
      -> build_ml_dataset (this module, the ONLY loader ML may use)
      -> validated ML dataset {features, outcomes, meta}

The layer structurally separates DECISION-TIME FEATURES (PIT-visible at
the decision timestamp) from RETROSPECTIVE OUTCOMES (evaluator-only).
Any outcome key present in the feature payload raises instead of being
silently carried. Missing feature legs stay None (never imputed); the
dataset manifest records per-feature missingness.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
from typing import Any, Dict, List, Mapping, Optional

# Frozen decision-time allowlist. Every entry was available to the
# agent/evaluator at the decision timestamp under the experiment's PIT
# policy. Extending this list requires a documented PIT justification.
DECISION_TIME_FEATURES = (
    "pre_trend_1d",
    "pre_trend_3d",
    "pre_trend_5d",
    "vix_tm1",
    "cash_before",
    "position_qty",
    "exposure_before",
    "avg_cost",
    "realized_pnl_before",
    "unrealized_pnl_before",
    "total_equity_before",
    "instrument",
    "action",
    "quantity",
)

# Retrospective outcomes. Must NEVER appear in a feature payload.
RETROSPECTIVE_OUTCOMES = (
    "forward_return_1d",
    "forward_return_3d",
    "mae",
    "mfe",
    "hold_return",
    "opportunity_return",
)

ADVERSE_BAND = 0.01


def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_ml_dataset(
    artefact_dirs: List[str],
    base_dir: str = ".",
    grid_bounds: Optional[Mapping[str, Mapping[str, str]]] = None,
) -> Dict[str, Any]:
    """Build the validated multi-window ML dataset (read-only over artefacts).

    Args:
        artefact_dirs: frozen E5a artefact directories (absolute or
            relative to base_dir).
        base_dir: repository root for the VIX lookup.
        grid_bounds: {experiment_id: {"start": ISO, "end": ISO}} used for
            the VIX t-1 join. Windows without bounds get vix_tm1=None
            with a manifest note (never a substitute value).

    Returns:
        {"rows": [...], "manifest": {...}} where each row carries
        "features" (allowlist only), "outcomes" (outcomes + labels),
        and "keys" (experiment/episode/decision identity).
    """
    import sys
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)
    from environment.indian.clock import build_master_grid, load_default_resolver
    from environment.indian.information_lookup import InformationLookup

    lookup = InformationLookup(base_dir=base_dir, strict=True)
    grids: Dict[str, List[str]] = {}
    if grid_bounds:
        resolver = load_default_resolver(base_dir)
        for exp_id, bounds in grid_bounds.items():
            grids[exp_id] = [d.isoformat() for d in build_master_grid(
                resolver, dt.date.fromisoformat(bounds["start"]),
                dt.date.fromisoformat(bounds["end"]))]

    rows: List[Dict[str, Any]] = []
    for artefact in artefact_dirs:
        path = artefact if os.path.isabs(artefact) else os.path.join(base_dir, artefact)
        exp_id = os.path.basename(os.path.normpath(path))
        with open(os.path.join(path, "decision_table.csv")) as handle:
            table = list(csv.DictReader(handle))
        with open(os.path.join(path, "baseline_result.json")) as handle:
            records = {r["decision_timestamp"] + "|" + str(i): r
                       for i, r in enumerate(json.load(handle)["decision_records"])}
        # Join portfolio detail (positions/pnl) by timestamp + row order
        # within timestamp: decision_table preserves trajectory order.
        order_in_session: Dict[str, int] = {}
        grid = grids.get(exp_id)
        for row in table:
            if row["participation_status"] != "EXECUTED":
                continue
            ts = row["decision_timestamp"]
            # NOTE: multi-order sessions share a timestamp; order index
            # follows file order (trajectory order preserved by engine).
            key_prefix = ts + "|"
            matches = sorted(k for k in records if k.startswith(key_prefix))
            rec = records[matches[order_in_session.get(ts, 0) % max(len(matches), 1)]] \
                if matches else None
            order_in_session[ts] = order_in_session.get(ts, 0) + 1

            before = (rec.get("portfolio_before", {}) if rec else {}) or {}
            positions = before.get("positions", {}) or {}
            pos = positions.get(f"nse_equity:{row['instrument']}",
                                positions.get(row["instrument"], {})) or {}
            vix = None
            if grid is not None and ts in grid:
                i = grid.index(ts)
                if i - 1 >= 0:
                    vix = lookup.bar_close("indiavix", None, grid[i - 1])

            features: Dict[str, Any] = {
                "pre_trend_1d": _num(row.get("pre_trend_1d")),
                "pre_trend_3d": _num(row.get("pre_trend_3d")),
                "pre_trend_5d": _num(row.get("pre_trend_5d")),
                "vix_tm1": vix,
                "cash_before": _num(row.get("cash_before")),
                "position_qty": _num(pos.get("quantity")),
                "exposure_before": _num(row.get("exposure_before")),
                "avg_cost": _num(pos.get("avg_cost")),
                "realized_pnl_before": _num(before.get("realized_pnl")),
                "unrealized_pnl_before": _num(before.get("unrealized_pnl")),
                "total_equity_before": _num(row.get("total_equity_before")),
                "instrument": row.get("instrument"),
                "action": row.get("action"),
                "quantity": _num(row.get("quantity")),
            }
            forbidden = set(features) & set(RETROSPECTIVE_OUTCOMES)
            if forbidden:
                raise ValueError(f"outcome leakage in features: {sorted(forbidden)}")
            outcomes: Dict[str, Any] = {
                "forward_return_1d": _num(row.get("forward_return_1d")),
                "forward_return_3d": _num(row.get("forward_return_3d")),
                "mae": _num(row.get("mae")),
                "mfe": _num(row.get("mfe")),
                "hold_return": _num(row.get("hold_return")),
                "opportunity_return": _num(row.get("opportunity_return")),
            }
            fwd3, mfe_ = outcomes["forward_return_3d"], outcomes["mae"]
            outcomes["adverse_forward_3d"] = (
                fwd3 < -ADVERSE_BAND) if fwd3 is not None else None
            outcomes["adverse_mae"] = (
                mfe_ < -ADVERSE_BAND) if mfe_ is not None else None
            rows.append({
                "keys": {
                    "experiment_id": row.get("experiment_id"),
                    "episode_id": row.get("episode_id"),
                    "decision_id": row.get("decision_id"),
                    "decision_timestamp": ts,
                    "attribution_status": row.get("attribution_status"),
                },
                "features": features,
                "outcomes": outcomes,
            })

    missing: Dict[str, int] = {}
    for name in DECISION_TIME_FEATURES:
        missing[name] = sum(1 for r in rows if r["features"].get(name) is None)
    manifest = {
        "n_rows": len(rows),
        "windows": sorted(set(r["keys"]["experiment_id"] for r in rows)),
        "feature_schema": list(DECISION_TIME_FEATURES),
        "outcome_schema": list(RETROSPECTIVE_OUTCOMES) + [
            "adverse_forward_3d", "adverse_mae"],
        "feature_missingness": missing,
        "adverse_band": ADVERSE_BAND,
        "builder": "evaluation/attribution/features.py:build_ml_dataset",
    }
    return {"rows": rows, "manifest": manifest}
