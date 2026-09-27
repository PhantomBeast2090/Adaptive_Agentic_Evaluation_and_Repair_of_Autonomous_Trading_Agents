"""Entry-timing benchmark (P2 follow-up; additive evaluator-side layer).

Locked definition (protocol §1), per EXECUTED BUY decision at session t:

    actual entry      = recorded execution price (frozen attribution leg)
    hypothetical entry = C_{t+1} (exact-bar close, next grid session)
    common horizon     = C_{t+3} (exact-bar close)

    actual_return_3d   = (C_{t+3} - exec) / exec
    next_day_return_2d = (C_{t+3} - C_{t+1}) / C_{t+1}
    timing_regret      = next_day_return_2d - actual_return_3d

Positive timing_regret: entering one session later would have realised
a better return over the common t+3 endpoint. This is a hypothetical
next-session entry timing benchmark — never "the trade the agent
should have made". The one-step hypothetical fill is acknowledged
explicitly; no fill is simulated beyond referencing the recorded
next-session close.

Reuse, not duplication: exact bars come from the frozen
DecisionAttributionEngine leg methods (instantiated read-only) over
each artefact's frozen grid; the engine itself is unmodified.
Missing C_{t+1}/C_{t+3} (or non-BUY) yields None — never interpolated,
never substituted, never fabricated.

Timing-adverse criterion: timing_regret > ADVERSE_BAND (0.01), reusing
the frozen research-contract band — a protocol choice fixed before any
TEST inspection, consistent with the existing miner philosophy.
"""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Any, Dict, List, Mapping, Optional

from environment.indian.clock import build_master_grid
from evaluation.attribution.engine import DecisionAttributionEngine
from evaluation.attribution.features import ADVERSE_BAND

TIMING_BAND = ADVERSE_BAND


def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def timing_of(action: Any, exec_price: Any, c_tp1: Any, c_tp3: Any,
              engine: DecisionAttributionEngine) -> Optional[float]:
    """Realised timing contrast; None when legs missing or non-BUY."""
    if str(action) != "BUY":
        return None
    ref, c1, c3 = _num(exec_price), _num(c_tp1), _num(c_tp3)
    if ref is None or ref <= 0 or c1 is None or c1 <= 0 or c3 is None:
        return None
    actual = engine._ret(c3, ref)
    nextday = engine._ret(c3, c1)
    if actual is None or nextday is None:
        return None
    return nextday - actual


def timing_adverse(regret: Optional[float],
                   band: float = TIMING_BAND) -> Optional[bool]:
    if regret is None:
        return None
    return regret > band


def build_timing_table(r1_dataset: Mapping[str, Any],
                       v1_dataset: Optional[Mapping[str, Any]] = None,
                       artefact_dirs: Optional[List[str]] = None,
                       base_dir: str = ".") -> Dict[str, Any]:
    """Join frozen R1 rows with timing legs resolved through the engine.

    Execution prices come from frozen ``attribution.json``
    decision_time_state legs; C_{t+1}/C_{t+3} from the engine's
    exact-bar lookup over each artefact's frozen grid. Conditioning
    features pass through untouched (instrument/action merged from
    frozen V1 as in the regret view).
    """
    if artefact_dirs is None:
        artefact_dirs = [
            "data/frozen_traces/E5A-deterministic-attribution-20260926",
            "data/frozen_traces/E5A-window2-20260926",
            "data/frozen_traces/E5A-window3-20260926",
        ]
    v1_by_id = {}
    if v1_dataset is not None:
        v1_by_id = {r["keys"]["decision_id"]: r
                    for r in v1_dataset["rows"]}
    engine = DecisionAttributionEngine(base_dir=base_dir)
    # Frozen per-artefact legs: (attributed decisions, session grid).
    legs: Dict[str, Dict[str, Any]] = {}
    for artefact in artefact_dirs:
        path = (artefact if os.path.isabs(artefact)
                else os.path.join(base_dir, artefact))
        with open(os.path.join(path, "attribution.json")) as h:
            attr = json.load(h)
        grid = [d.isoformat() for d in build_master_grid(
            engine.resolver,
            date.fromisoformat(attr["grid_start"]),
            date.fromisoformat(attr["grid_end"]))]
        by_id = {d["decision_id"]: d
                 for d in attr["attributed_decisions"]}
        legs[attr["experiment_id"]] = {"decisions": by_id, "grid": grid}

    rows: List[Dict[str, Any]] = []
    for r in r1_dataset["rows"]:
        feats = dict(r["features"])
        v1f = (v1_by_id.get(r["keys"]["decision_id"], {})
               .get("features", {}))
        for field in ("instrument", "action"):
            if field not in feats and field in v1f:
                feats[field] = v1f[field]
        for forbidden in ("forward_return_1d", "forward_return_3d", "mae",
                          "mfe", "hold_return", "opportunity_return",
                          "regret_3d", "timing_regret"):
            if forbidden in feats:
                raise ValueError(
                    f"evaluator-only field in conditioning X: {forbidden}")
        action = feats.get("action")
        if action is None:
            raise ValueError(
                f"missing action for {r['keys']['decision_id']}")
        exp_id = r["keys"]["experiment_id"]
        aero = legs[exp_id]["decisions"].get(r["keys"]["decision_id"], {})
        state = aero.get("decision_time_state", {}) or {}
        ts = r["keys"]["decision_timestamp"]
        grid = legs[exp_id]["grid"]
        c1 = engine._close(
            "nse_equity", str(feats.get("instrument") or ""),
            engine._shift_date(ts, 1, grid))
        c3 = engine._close(
            "nse_equity", str(feats.get("instrument") or ""),
            engine._shift_date(ts, 3, grid))
        treg = timing_of(action, state.get("execution_price"), c1, c3,
                         engine)
        rows.append({
            "keys": dict(r["keys"]),
            "features": feats,
            "timing_regret": treg,
            "timing_adverse": timing_adverse(treg),
            "legs": {"execution_price": state.get("execution_price"),
                     "c_tp1": c1, "c_tp3": c3,
                     "action": action},
        })
    rows.sort(key=lambda r: (r["keys"]["decision_timestamp"],
                             r["keys"]["decision_id"]))
    labelled = sum(1 for r in rows if r["timing_adverse"] is not None)
    return {"rows": rows, "manifest": {
        "n_rows": len(rows),
        "n_timing_labelled": labelled,
        "n_timing_missing": len(rows) - labelled,
        "timing_band": TIMING_BAND,
        "timing_definition": "(C_t+3 - C_t+1)/C_t+1 - (C_t+3 - exec)/exec "
                             "(BUY only; hypothetical next-session entry)",
        "benchmark_caveat": "one-step hypothetical fill acknowledged; "
                            "never described as the trade to make",
        "builder": "evaluation/attribution/timing.py:build_timing_table",
    }}


def load_r1(base_dir: str) -> Dict[str, Any]:
    path = os.path.join(
        base_dir, "data", "frozen_traces", "_ml_sequence",
        "e5a_combined_v3.json")
    with open(path) as h:
        return json.load(h)
