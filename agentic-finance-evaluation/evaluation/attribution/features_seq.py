"""V3 sequence-feature builder (M4 representation experiment).

Additive layer BESIDE V1/V2. Builds trailing trajectory summaries from
the frozen ``baseline_result.json`` decision-record order: for an
EXECUTED row matched to record index ``i``, history = records[0:i]
(strictly earlier trajectory order — never the current record, never
later records). Windows k=3 and k=5 over available history; short
history aggregates over what exists; zero history stays None (never
forward-filled, never fabricated).

PIT doctrine: prior records' portfolio snapshots, submitted orders,
and realised rewards all occurred strictly before T and are legitimate
decision-time-observable history. The current record's reward,
executions, and all decision_table outcome columns NEVER enter X
(RETROSPECTIVE_OUTCOMES guard mirrors V1/V2).

Frozen V3 allowlist: 24 features. No post-hoc extension.
"""

from __future__ import annotations

import csv
import json
import os
from typing import Any, Dict, List, Mapping, Optional, Tuple

from evaluation.attribution.features import ADVERSE_BAND, RETROSPECTIVE_OUTCOMES

K_WINDOWS = (3, 5)

SEQ_FEATURES = (
    # A. recent action history (prior submitted_orders sides)
    "seq_n_prev_k3",
    "seq_n_prev_k5",
    "seq_buy_count_k3",
    "seq_buy_count_k5",
    "seq_exec_freq_k3",
    "seq_exec_freq_k5",
    "seq_action_persistence_k3",
    "seq_action_persistence_k5",
    # B. exposure trajectory (prior + current portfolio_before.exposure)
    "seq_exposure_change_k3",
    "seq_exposure_change_k5",
    "seq_exposure_mean_k3",
    "seq_exposure_mean_k5",
    "seq_exposure_slope_k3",
    "seq_exposure_slope_k5",
    # C. cash trajectory
    "seq_cash_change_k3",
    "seq_cash_change_k5",
    "seq_cash_min_k3",
    "seq_cash_min_k5",
    # D. portfolio trajectory
    "seq_equity_change_k3",
    "seq_equity_change_k5",
    "seq_realized_pnl_change_k3",
    "seq_realized_pnl_change_k5",
    # E. reward trajectory (prior records' realised rewards only)
    "seq_reward_mean_k3",
    "seq_reward_mean_k5",
)

SEQ_PROVENANCE: Dict[str, Dict[str, str]] = {
    name: {
        "source": "frozen baseline_result.json decision_records "
                  "(portfolio_before / submitted_orders / reward)",
        "pit_rule": "records with trajectory index strictly < current "
                    "record index; last k of those",
        "derivation": _deriv,
        "agent_observes": "no (derivable from own portfolio history)",
        "missingness": "None when zero prior records in scope",
    }
    for name, _deriv in [
        ("seq_n_prev_k3", "count of prior records in k=3 scope (support)"),
        ("seq_n_prev_k5", "count of prior records in k=5 scope (support)"),
        ("seq_buy_count_k3", "BUY sides among prior submitted_orders"),
        ("seq_buy_count_k5", "BUY sides among prior submitted_orders"),
        ("seq_exec_freq_k3", "fraction of prior records with >=1 order"),
        ("seq_exec_freq_k5", "fraction of prior records with >=1 order"),
        ("seq_action_persistence_k3",
         "fraction of prior records sharing current dominant side"),
        ("seq_action_persistence_k5",
         "fraction of prior records sharing current dominant side"),
        ("seq_exposure_change_k3", "exposure(T) - exposure(oldest in scope)"),
        ("seq_exposure_change_k5", "exposure(T) - exposure(oldest in scope)"),
        ("seq_exposure_mean_k3", "mean prior exposure in scope"),
        ("seq_exposure_mean_k5", "mean prior exposure in scope"),
        ("seq_exposure_slope_k3", "OLS slope of prior exposure vs order"),
        ("seq_exposure_slope_k5", "OLS slope of prior exposure vs order"),
        ("seq_cash_change_k3", "cash(T) - cash(oldest in scope)"),
        ("seq_cash_change_k5", "cash(T) - cash(oldest in scope)"),
        ("seq_cash_min_k3", "min prior cash in scope"),
        ("seq_cash_min_k5", "min prior cash in scope"),
        ("seq_equity_change_k3", "equity(T) - equity(oldest in scope)"),
        ("seq_equity_change_k5", "equity(T) - equity(oldest in scope)"),
        ("seq_realized_pnl_change_k3", "realized(T) - realized(oldest)"),
        ("seq_realized_pnl_change_k5", "realized(T) - realized(oldest)"),
        ("seq_reward_mean_k3", "mean prior realised reward in scope"),
        ("seq_reward_mean_k5", "mean prior realised reward in scope"),
    ]
}


def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _slope(xs: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mean_i = (n - 1) / 2.0
    mean_x = sum(xs) / n
    denom = sum((i - mean_i) ** 2 for i in range(n))
    if denom == 0:
        return None
    return sum((i - mean_i) * (x - mean_x)
               for i, x in enumerate(xs)) / denom


def _dominant_side(orders: List[Mapping[str, Any]]) -> Optional[str]:
    sides = [str(o.get("side")) for o in orders or [] if o.get("side")]
    if not sides:
        return None
    return max(set(sides), key=sides.count)


def _window_features(prior: List[Mapping[str, Any]],
                     cur_before: Mapping[str, Any],
                     cur_side: Optional[str],
                     k: int) -> Dict[str, Any]:
    scope = prior[-k:]
    n = len(scope)
    out: Dict[str, Any] = {f"seq_n_prev_k{k}": float(n)}
    if n == 0:
        for name in SEQ_FEATURES:
            if name.endswith(f"_k{k}") and not name.startswith("seq_n_prev"):
                out[name] = None
        return out
    # A. action history
    buy = sum(1 for r in scope for o in (r.get("submitted_orders") or [])
              if str(o.get("side")) == "BUY")
    acted = sum(1 for r in scope if r.get("submitted_orders"))
    out[f"seq_buy_count_k{k}"] = float(buy)
    out[f"seq_exec_freq_k{k}"] = acted / n
    if cur_side is None:
        out[f"seq_action_persistence_k{k}"] = None
    else:
        same = sum(1 for r in scope
                   if _dominant_side(r.get("submitted_orders") or [])
                   == cur_side)
        voiced = sum(1 for r in scope
                     if _dominant_side(r.get("submitted_orders") or [])
                     is not None)
        out[f"seq_action_persistence_k{k}"] = (
            same / voiced if voiced else None)
    # B/C/D trajectories over prior portfolio_before (+ current anchor)
    expos = [_num(r.get("portfolio_before", {}).get("exposure"))
             for r in scope]
    expos = [e for e in expos if e is not None]
    cur_exp = _num(cur_before.get("exposure"))
    out[f"seq_exposure_mean_k{k}"] = (
        sum(expos) / len(expos) if expos else None)
    out[f"seq_exposure_slope_k{k}"] = _slope(expos)
    out[f"seq_exposure_change_k{k}"] = (
        cur_exp - expos[0] if cur_exp is not None and expos else None)

    def _change(field: str) -> Optional[float]:
        vals = [_num(r.get("portfolio_before", {}).get(field))
                for r in scope]
        vals = [v for v in vals if v is not None]
        cur = _num(cur_before.get(field))
        return cur - vals[0] if cur is not None and vals else None

    out[f"seq_cash_change_k{k}"] = _change("cash")
    cashes = [_num(r.get("portfolio_before", {}).get("cash"))
              for r in scope]
    cashes = [c for c in cashes if c is not None]
    out[f"seq_cash_min_k{k}"] = min(cashes) if cashes else None
    out[f"seq_equity_change_k{k}"] = _change("total_equity")
    out[f"seq_realized_pnl_change_k{k}"] = _change("realized_pnl")
    rews = [_num(r.get("reward")) for r in scope]
    rews = [v for v in rews if v is not None]
    out[f"seq_reward_mean_k{k}"] = (
        sum(rews) / len(rews) if rews else None)
    return out


def build_sequence_features(
    artefact_dirs: List[str],
    base_dir: str = ".",
) -> Dict[str, Any]:
    """Build V3 sequence features (read-only over frozen artefacts)."""
    rows: List[Dict[str, Any]] = []
    for artefact in artefact_dirs:
        path = (artefact if os.path.isabs(artefact)
                else os.path.join(base_dir, artefact))
        with open(os.path.join(path, "decision_table.csv"), newline="") as h:
            table = list(csv.DictReader(h))
        with open(os.path.join(path, "baseline_result.json")) as h:
            records = list(json.load(h)["decision_records"])
        order_in_session: Dict[str, int] = {}
        for row in table:
            if row["participation_status"] != "EXECUTED":
                continue
            ts = row["decision_timestamp"]
            # Replicate the V1/V2 trajectory join: file order is
            # trajectory order; same-timestamp rows follow file order.
            same_ts = [i for i, r in enumerate(records)
                       if r["decision_timestamp"] == ts]
            idx = (same_ts[order_in_session.get(ts, 0) % len(same_ts)]
                   if same_ts else None)
            order_in_session[ts] = order_in_session.get(ts, 0) + 1
            if idx is None:
                continue
            rec = records[idx]
            prior = records[:idx]  # strictly earlier trajectory state
            cur_before = rec.get("portfolio_before", {}) or {}
            cur_side = str(row.get("action") or "") or None
            features: Dict[str, Any] = {}
            for k in K_WINDOWS:
                features.update(
                    _window_features(prior, cur_before, cur_side, k))
            if set(features) != set(SEQ_FEATURES):
                raise ValueError("V3 schema drift: %s" % sorted(
                    set(features) ^ set(SEQ_FEATURES)))
            forbidden = set(features) & set(RETROSPECTIVE_OUTCOMES)
            if forbidden:
                raise ValueError(
                    f"outcome leakage in V3 features: {sorted(forbidden)}")
            rows.append({
                "keys": {
                    "experiment_id": row.get("experiment_id"),
                    "episode_id": row.get("episode_id"),
                    "decision_id": row.get("decision_id"),
                    "decision_timestamp": ts,
                    "record_index": idx,
                    "n_prior_records": len(prior),
                },
                "features": features,
            })
    missing = {n: sum(1 for r in rows if r["features"].get(n) is None)
               for n in SEQ_FEATURES}
    return {"rows": rows, "manifest": {
        "n_rows": len(rows),
        "windows": sorted(set(r["keys"]["experiment_id"] for r in rows)),
        "feature_schema": list(SEQ_FEATURES),
        "feature_missingness": missing,
        "k_windows": list(K_WINDOWS),
        "provenance": SEQ_PROVENANCE,
        "adverse_band": ADVERSE_BAND,
        "builder": "evaluation/attribution/features_seq.py:"
                   "build_sequence_features",
    }}
