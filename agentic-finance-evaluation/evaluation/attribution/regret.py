"""Counterfactual-regret diagnostic view (P2 diagnosis experiment).

Additive derived view over frozen E5A attribution legs. For an EXECUTED
BUY decision:

    regret_3d = hold_return_3d - forward_return_3d

Positive regret = holding/waiting outperformed the executed BUY;
negative regret = the BUY outperformed the hold comparator.

Cost semantics (documented limitation, §2 of the protocol): both legs
are gross price-path returns — forward from the recorded execution
price, hold from the pre-decision close. Neither leg deducts the
recorded transaction costs, and the BUY leg alone paid them, so raw
regret is CONSERVATIVE against finding BUY inferior. No new cost model
is introduced in this milestone.

Counterfactual status: a realised evaluator-side contrast between two
recorded price paths (executed fill vs pre-decision close carried
forward). No alternative execution is simulated; NOOP sessions keep
regret None ("no counterfactual trade invented", engine convention).

Regret-adverse criterion: regret_3d > ADVERSE_BAND (0.01), reusing the
frozen research-contract band as an economically interpretable
threshold — a protocol choice, not a fitted parameter. SELL rows, if
ever present, receive regret None ("SELL semantics not
pre-registered") rather than assumed BUY semantics.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Mapping, Optional

from evaluation.attribution.features import ADVERSE_BAND

REGRET_BAND = ADVERSE_BAND
REGRET_HORIZON = 3


def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def regret_of(action: Any, forward_3d: Any, hold_3d: Any) -> Optional[float]:
    """Realised BUY-vs-HOLD contrast; None when legs missing or non-BUY."""
    if str(action) != "BUY":
        return None
    fwd, hold = _num(forward_3d), _num(hold_3d)
    if fwd is None or hold is None:
        return None
    return hold - fwd


def regret_adverse(regret: Optional[float],
                   band: float = REGRET_BAND) -> Optional[bool]:
    if regret is None:
        return None
    return regret > band


def build_regret_table(r1_dataset: Mapping[str, Any],
                       v1_dataset: Optional[Mapping[str, Any]] = None
                       ) -> Dict[str, Any]:
    """Join frozen R1 rows (V2+sequence features) with regret legs.

    R1 rows carry no instrument/action (frozen V2 schema); when
    ``v1_dataset`` is supplied those two decision-time fields are
    merged from frozen V1 by decision_id for conditioning and support
    reporting. The only new columns are ``regret_3d`` and
    ``regret_adverse``. Conditioning features pass through untouched.
    """
    v1_by_id = {}
    if v1_dataset is not None:
        v1_by_id = {r["keys"]["decision_id"]: r
                    for r in v1_dataset["rows"]}
    rows: List[Dict[str, Any]] = []
    for r in r1_dataset["rows"]:
        feats = dict(r["features"])
        v1f = (v1_by_id.get(r["keys"]["decision_id"], {})
               .get("features", {}))
        for field in ("instrument", "action"):
            if field not in feats and field in v1f:
                feats[field] = v1f[field]
        # Conditioning guard: evaluator-only quantities stay out of X.
        for forbidden in ("forward_return_1d", "forward_return_3d", "mae",
                          "mfe", "hold_return", "opportunity_return",
                          "regret_3d", "regret_adverse"):
            if forbidden in feats:
                raise ValueError(
                    f"evaluator-only field in conditioning X: {forbidden}")
        action = feats.get("action")
        if action is None:
            # No instrument/action anywhere frozen: fail closed, never
            # assume BUY semantics.
            raise ValueError(
                f"missing action for {r['keys']['decision_id']}")
        outcomes = r["outcomes"]
        regret = regret_of(action, outcomes.get("forward_return_3d"),
                           outcomes.get("hold_return"))
        rows.append({
            "keys": dict(r["keys"]),
            "features": dict(feats),
            "regret_3d": regret,
            "regret_adverse": regret_adverse(regret),
            "legs": {"forward_return_3d": outcomes.get("forward_return_3d"),
                     "hold_return": outcomes.get("hold_return"),
                     "action": action},
        })
    rows.sort(key=lambda r: (r["keys"]["decision_timestamp"],
                             r["keys"]["decision_id"]))
    labelled = sum(1 for r in rows if r["regret_adverse"] is not None)
    return {"rows": rows, "manifest": {
        "n_rows": len(rows),
        "n_regret_labelled": labelled,
        "n_regret_missing": len(rows) - labelled,
        "regret_band": REGRET_BAND,
        "regret_definition": "hold_return_3d - forward_return_3d (BUY only)",
        "cost_note": "gross legs; BUY paid costs, HOLD did not "
                     "(conservative against BUY inferiority)",
        "builder": "evaluation/attribution/regret.py:build_regret_table",
    }}


def load_r1(base_dir: str) -> Dict[str, Any]:
    path = os.path.join(
        base_dir, "data", "frozen_traces", "_ml_sequence",
        "e5a_combined_v3.json")
    with open(path) as h:
        return json.load(h)
