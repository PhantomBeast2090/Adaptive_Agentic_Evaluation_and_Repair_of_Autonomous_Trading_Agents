"""Evaluator-side diagnostic join (the ONLY retrospective contact point).

Combines, per decision:
  * OBSERVED decision-time context (V1/V2 features + portfolio snapshots),
  * MODEL_DERIVED forecast features (from ForecastOutput only),
  * EVALUATOR_ONLY outcomes (adverse labels, forward returns, MAE/MFE).

Outcomes enter here and nowhere upstream. Every field carries a
provenance tag so no future outcome can accidentally become an
agent-visible input downstream.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

OBSERVED = "OBSERVED"
MODEL_DERIVED = "MODEL_DERIVED"
EVALUATOR_ONLY = "EVALUATOR_ONLY"
INFERRED = "INFERRED"

# Fixed diagnostic column contract (authorised; frozen before comparison).
MINER_NUMERIC_COLUMNS = (
    "f_ret_1d", "f_ret_3d", "f_ret_5d",
    "f_q10_5d_ret", "f_q90_5d_ret",
    "f_interval_width_5d", "f_downside_prob",
    "f_slope", "f_curvature", "f_dispersion",
    "f_direction_consistency",
    "nifty_return_5d", "vix_change_5d",
    "instrument_return_5d", "drawdown",
)
MINER_CATEGORICAL_COLUMNS = ("instrument",)


def build_diagnostic_table(
    v1_rows: List[Mapping[str, Any]],
    v2_rows: List[Mapping[str, Any]],
    forecast_rows: Mapping[str, Mapping[str, Any]],
    target: str = "adverse_mae",
) -> Dict[str, Any]:
    """Join the three evidence legs by decision_id (read-only)."""
    v1 = {r["keys"]["decision_id"]: r for r in v1_rows}
    v2 = {r["keys"]["decision_id"]: r for r in v2_rows}
    rows: List[Dict[str, Any]] = []
    for did, base in v1.items():
        if did not in v2:
            continue
        feats: Dict[str, Any] = {}
        provenance: Dict[str, str] = {}
        for col in MINER_NUMERIC_COLUMNS + MINER_CATEGORICAL_COLUMNS:
            if col.startswith("f_"):
                val = (forecast_rows.get(did) or {}).get(col)
                feats[col] = val
                provenance[col] = MODEL_DERIVED
            elif col == "instrument":
                feats[col] = base["features"].get("instrument")
                provenance[col] = OBSERVED
            else:
                src = v2[did]["features"]
                feats[col] = src.get(col)
                provenance[col] = OBSERVED
        outcome = base["outcomes"].get(target)
        rows.append({
            "keys": dict(base["keys"]),
            "features": feats,
            "feature_provenance": provenance,
            "outcome": outcome,
            "outcome_provenance": EVALUATOR_ONLY,
            "target": target,
        })
    rows.sort(key=lambda r: (r["keys"]["decision_timestamp"],
                             r["keys"]["decision_id"]))
    return {"rows": rows,
            "manifest": {"n_rows": len(rows), "target": target,
                         "numeric_columns": list(MINER_NUMERIC_COLUMNS),
                         "categorical_columns": list(
                             MINER_CATEGORICAL_COLUMNS)}}
