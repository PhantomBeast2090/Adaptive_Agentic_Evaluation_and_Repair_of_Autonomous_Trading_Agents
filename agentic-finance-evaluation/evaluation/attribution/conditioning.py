"""E5a conditioning analysis (read-only over frozen artefacts).

Produces the machine-readable companion (conditioning.json) for one E5a
window without altering the frozen trajectory. All thresholds are the
frozen E5A definitions; bands are transparent (±0.01) and reported with
N/count/rate — effect sizes first, no significance hunting.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
from collections import Counter
from typing import Any, Dict, List, Optional

ADVERSE_BAND = 0.01


def load_rows(artefact_dir: str) -> List[Dict[str, Any]]:
    with open(os.path.join(artefact_dir, "decision_table.csv")) as handle:
        return list(csv.DictReader(handle))


def load_baseline_records(artefact_dir: str) -> List[Dict[str, Any]]:
    with open(os.path.join(artefact_dir, "baseline_result.json")) as handle:
        return json.load(handle)["decision_records"]


def trend_band(value: Optional[str]) -> str:
    if value in ("", None):
        return "missing"
    v = float(value)
    if v < -ADVERSE_BAND:
        return "negative"
    if v > ADVERSE_BAND:
        return "positive"
    return "flat"


def _rate(rows: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    n = len(rows)
    c = sum(1 for r in rows if r[key])
    return {"n": n, "count": c, "rate": (c / n if n else None)}


def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def analyze_window(
    artefact_dir: str,
    base_dir: str = ".",
    vix_lookup: Any = None,
    grid: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Conditioning summary for one frozen E5a window (read-only)."""
    rows = load_rows(artefact_dir)
    exe = [r for r in rows if r["participation_status"] == "EXECUTED"]
    noop = [r for r in rows if r["participation_status"] != "EXECUTED"]
    for r in exe:
        fwd = _num(r.get("forward_return_3d"))
        mae = _num(r.get("mae"))
        # Missing legs stay None: never scored as non-adverse. Base rates
        # below report populated denominators alongside raw counts.
        r["af3"] = (fwd < -ADVERSE_BAND) if fwd is not None else None
        r["amae"] = (mae < -ADVERSE_BAND) if mae is not None else None

    out: Dict[str, Any] = {
        "n_rows": len(rows),
        "n_executed": len(exe),
        "n_noop": len(noop),
        "sessions": sorted(set(r["decision_timestamp"] for r in rows)),
        "participation": dict(Counter(r["participation_status"] for r in rows)),
        "attribution": dict(Counter(r["attribution_status"] for r in rows)),
        "actions": dict(Counter(r["action"] for r in exe)),
        "instruments": dict(Counter(r["instrument"] for r in exe)),
        "base_adverse_forward_3d": _rate(exe, "af3"),
        "base_adverse_mae": _rate(exe, "amae"),
        "populated_adverse_forward_3d": _rate(
            [r for r in exe if r["af3"] is not None], "af3"),
        "populated_adverse_mae": _rate(
            [r for r in exe if r["amae"] is not None], "amae"),
        "leg_coverage": {},
        "pre_trend_conditioning": {},
        "instrument_conditioning": {},
        "temporal_conditioning": {},
        "exposure_conditioning": {},
        "vix_conditioning": {},
    }
    for col in ("pre_trend_1d", "pre_trend_3d", "pre_trend_5d",
                "forward_return_1d", "forward_return_3d", "mae", "mfe",
                "hold_return", "opportunity_return"):
        cov = sum(1 for r in exe if r[col] not in ("", None))
        out["leg_coverage"][col] = {"populated": cov, "n": len(exe)}

    for col in ("pre_trend_1d", "pre_trend_3d", "pre_trend_5d"):
        bands: Dict[str, Any] = {}
        for b in ("negative", "flat", "positive", "missing"):
            s = [r for r in exe if trend_band(r[col]) == b]
            bands[b] = {"forward_3d": _rate(s, "af3"), "mae": _rate(s, "amae")}
        out["pre_trend_conditioning"][col] = bands

    for inst in sorted(set(r["instrument"] for r in exe)):
        s = [r for r in exe if r["instrument"] == inst]
        out["instrument_conditioning"][inst] = {
            "forward_3d": _rate(s, "af3"), "mae": _rate(s, "amae")}

    sess = sorted(set(r["decision_timestamp"] for r in exe))
    k = max(len(sess) // 3, 1)
    for name, ss in (("early", sess[:k]), ("mid", sess[k:2 * k]),
                     ("late", sess[2 * k:])):
        s = [r for r in exe if r["decision_timestamp"] in ss]
        out["temporal_conditioning"][name] = {
            "sessions": ss,
            "forward_3d": _rate(s, "af3"), "mae": _rate(s, "amae")}

    es = sorted((r for r in exe if _num(r.get("exposure_before")) is not None),
                key=lambda r: float(r["exposure_before"]))
    out["exposure_missing_n"] = len(exe) - len(es)
    if es:
        k = max(len(es) // 3, 1)
        for name, s in (("low", es[:k]), ("mid", es[k:2 * k]),
                        ("high", es[2 * k:])):
            out["exposure_conditioning"][name] = {
                "range": [s[0]["exposure_before"], s[-1]["exposure_before"]],
                "forward_3d": _rate(s, "af3"), "mae": _rate(s, "amae")}

    if vix_lookup is not None and grid is not None:
        for r in exe:
            i = grid.index(r["decision_timestamp"])
            r["vix"] = (vix_lookup.bar_close("indiavix", None, grid[i - 1])
                        if i - 1 >= 0 else None)
        vs = sorted((r for r in exe if r["vix"]), key=lambda r: r["vix"])
        out["vix_missing_n"] = sum(1 for r in exe if not r.get("vix"))
        if vs:
            k = max(len(vs) // 3, 1)
            for name, s in (("low", vs[:k]), ("mid", vs[k:2 * k]),
                            ("high", vs[2 * k:])):
                out["vix_conditioning"][name] = {
                    "range": [s[0]["vix"], s[-1]["vix"]],
                    "forward_3d": _rate(s, "af3"), "mae": _rate(s, "amae")}
    return out


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="E5a conditioning (read-only)")
    parser.add_argument("--artefact-dir", required=True)
    parser.add_argument("--out", required=True,
                        help="Output conditioning.json path (outside frozen artefact)")
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--grid-start", required=True)
    parser.add_argument("--grid-end", required=True)
    args = parser.parse_args()

    import sys
    sys.path.insert(0, args.base_dir)
    from environment.indian.clock import build_master_grid, load_default_resolver
    from environment.indian.information_lookup import InformationLookup

    lookup = InformationLookup(base_dir=args.base_dir, strict=True)
    grid = [d.isoformat() for d in build_master_grid(
        load_default_resolver(args.base_dir),
        dt.date.fromisoformat(args.grid_start),
        dt.date.fromisoformat(args.grid_end))]
    summary = analyze_window(args.artefact_dir, args.base_dir, lookup, grid)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, sort_keys=True, indent=2)
        handle.write("\n")
    print(f"conditioning: n={summary['n_rows']} "
          f"af3={summary['base_adverse_forward_3d']} "
          f"amae={summary['base_adverse_mae']} -> {args.out}")


if __name__ == "__main__":
    main()
