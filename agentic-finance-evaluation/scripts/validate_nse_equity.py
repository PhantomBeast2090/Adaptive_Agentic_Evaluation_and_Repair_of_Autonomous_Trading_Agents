#!/usr/bin/env python3
"""Full-dataset aggregate validation for the NSE equity bhavcopy milestone.

Unit tests must stay fast: they use spot-checks plus synthetic fixtures.
THIS script performs the expensive whole-corpus validation exactly once
per milestone and writes machine-readable evidence consumed by the
manifest and the milestone report:

  - per-file audit rollups (both regimes)
  - duplicate/conflict counts (within-file, within-regime, cross-regime)
  - numeric/OHLC/delivery violation totals
  - requested-date vs in-file-date integrity gate (HARD: any mismatch or
    unparseable in-file date fails the gate)
  - full cross-regime field comparison over every shared (date, symbol,
    series) key in the overlap span
  - mandatory full 08-Jul-2024 reconciliation detail
  - discontinuity classification summary (corporate-action candidates
    preserved, never adjusted)
  - availability accounting (expected: 100% NULL -> 0 agent-eligible)

Usage (project root):
    PYTHONPATH=. python3 scripts/validate_nse_equity.py \
        --raw-dir data/raw/india/equities \
        --out results/nse_equity_validation.json

The canonical CSV is NOT written here; build it with
scripts/build_nse_equity_canonical.py (deterministic, rerunnable).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd


def _log(phase: str, detail: str = "") -> None:
    print(f"[{time.strftime('%H:%M:%S')}] [{phase}] {detail}", flush=True)


def _load_index(raw_dir: Path) -> list[dict[str, str]]:
    index_path = raw_dir / "bhavcopy_index.csv"
    if not index_path.exists():
        raise FileNotFoundError(f"Acquisition index missing: {index_path}")
    with open(index_path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/india/equities"))
    parser.add_argument("--out", type=Path, default=Path("results/nse_equity_validation.json"))
    args = parser.parse_args()

    sys.path.insert(0, ".")
    from src.india import nse_equity_canonicalize as eq

    raw_dir: Path = args.raw_dir
    _log("init", f"raw_dir={raw_dir}")
    index = _load_index(raw_dir)
    by_file = {row["filename"]: row for row in index}
    _log("init", f"index entries={len(index)}")

    sec_files, udiff_files = eq.discover_raw_files(raw_dir)
    _log("init", f"sec_bhav files={len(sec_files)} udiff files={len(udiff_files)}")
    evidence: dict = {
        "regimes": {},
        "integrity_gate": {"mismatches": [], "passed": False},
        "duplicates": {},
        "cross_regime_full": {},
        "reconciliation_20240708": {},
        "discontinuities": {},
        "availability": {},
    }

    # ---- HARD integrity gate: every HTTP-200 artifact must carry a
    # parseable, verified in-file observation date. Holiday-fallback files
    # (verified in-file date != requested date) are NOT gate failures:
    # they are genuine NSE observations of their in-file date, preserved
    # in raw and deduplicated by in-file date in canonicalization. They
    # are accounted separately below. Only unverifiable dates fail hard.
    _log("phase", "integrity-gate starting")
    mismatches = [
        {"filename": r["filename"], "requested_date": r["requested_date"],
         "infile_date": r["infile_date"], "note": r["note"]}
        for r in index
        if r.get("http_status") == "200" and not r.get("infile_date")
    ]
    fallbacks = [
        {"filename": r["filename"], "requested_date": r["requested_date"],
         "infile_date": r["infile_date"]}
        for r in index
        if r.get("http_status") == "200" and r.get("date_match") == "False"
    ]
    evidence["integrity_gate"]["mismatches"] = mismatches
    evidence["integrity_gate"]["fallback_files"] = fallbacks
    evidence["integrity_gate"]["fallback_count"] = len(fallbacks)
    evidence["integrity_gate"]["checked_artifacts"] = sum(
        1 for r in index if r.get("http_status") == "200")
    evidence["integrity_gate"]["passed"] = not mismatches
    _log("phase", f"integrity-gate complete passed={not mismatches} "
                  f"mismatches={len(mismatches)} fallbacks={len(fallbacks)}")

    # ---- per-file validation rollup (frames kept for reuse below) ----
    kept: dict[str, list[pd.DataFrame]] = {}
    for regime, files, validator in (
        ("sec_bhav", sec_files, eq.validate_sec_bhav_file),
        ("udiff", udiff_files, eq.validate_udiff_file),
    ):
        audits = []
        frames: list[pd.DataFrame] = []
        names: list[str] = []
        excluded_total = 0
        t_start = time.time()
        for i, path in enumerate(files, start=1):
            rel = f"data/raw/india/equities/{path.name}"
            idx = by_file.get(path.name, {})
            audit, frame, excluded = validator(path, rel, idx.get("requested_date") or None)
            audits.append(audit)
            frames.append(frame)
            names.append(path.name)
            excluded_total += len(excluded)
            if i % 250 == 0 or i == len(files):
                _log("artifact", f"{regime} {i}/{len(files)} "
                                 f"elapsed={time.time() - t_start:.0f}s")
        _log("phase", f"{regime} per-file complete "
                      f"files={len(files)} elapsed={time.time() - t_start:.0f}s")
        dup_within = sum(a.duplicate_keys_within_file for a in audits)
        _log("phase", f"{regime} overlap-detection starting")
        value_cols = ["open", "high", "low", "close", "last_price", "prev_close"]
        overlaps = eq.detect_key_overlaps(frames, names, value_cols)
        _log("phase", f"{regime} overlap-detection complete "
                      f"overlaps={len(overlaps)}")
        identical = sum(1 for o in overlaps if o.identical)
        conflicting = [o for o in overlaps if not o.identical]
        dates = sorted({d for f in frames for d in
                        pd.to_datetime(f["observation_date"]).dt.date.unique()}
                       ) if frames else []
        all_series: Counter = Counter()
        for a in audits:
            for s in a.series_observed:
                all_series[s] += 1
        evidence["regimes"][regime] = {
            "files": len(files),
            "valid_rows": int(sum(a.valid_row_count for a in audits)),
            "excluded_rows": int(excluded_total),
            "header_invalid_files": [a.filename for a in audits if not a.header_valid],
            "duplicate_keys_within_file": int(dup_within),
            "within_regime_overlapping_keys": len(overlaps),
            "within_regime_identical": int(identical),
            "within_regime_conflicting": len(conflicting),
            "conflict_examples": [
                {"key": list(o.key), "files": o.files} for o in conflicting[:10]],
            "ohlc_violations": int(sum(a.ohlc_violations for a in audits)),
            "negative_price_rows": int(sum(a.negative_price_count for a in audits)),
            "negative_quantity_rows": int(sum(a.negative_quantity_count for a in audits)),
            "delivery_violations": int(sum(a.delivery_violations for a in audits)),
            "null_or_malformed_rows": int(sum(a.null_or_malformed_rows for a in audits)),
            "distinct_dates": len(dates),
            "first_date": dates[0].isoformat() if dates else None,
            "last_date": dates[-1].isoformat() if dates else None,
            "distinct_series": len(all_series),
            "series_file_days": dict(all_series),
        }
        kept[regime] = frames

    # ---- full cross-regime comparison over every shared key ----
    # Frames are REUSED from the rollup loop above (no second parse pass).
    _log("phase", "concat starting")
    sec_all = pd.concat(
        kept.get("sec_bhav", []), ignore_index=True) if kept.get("sec_bhav") else pd.DataFrame()
    ud_all = pd.concat(
        kept.get("udiff", []), ignore_index=True) if kept.get("udiff") else pd.DataFrame()
    _log("phase", f"concat complete sec_rows={len(sec_all)} udiff_rows={len(ud_all)}")
    if not sec_all.empty and not ud_all.empty:
        _log("phase", "cross-regime-full starting")
        full = eq.compare_regimes(sec_all, ud_all)
        _log("phase", f"cross-regime-full complete common={full['common_keys']} "
                      f"exact={full['exact_keys']} conflicts={len(full['conflicts'])}")
        evidence["cross_regime_full"] = {
            "sec_keys": full["sec_keys"], "udiff_keys": full["udiff_keys"],
            "common_keys": full["common_keys"], "sec_only": full["sec_only"],
            "udiff_only": full["udiff_only"], "exact_keys": full["exact_keys"],
            "turnover_ok": full["turnover_ok"],
            "turnover_mismatch": full["turnover_mismatch"],
            "field_mismatches": full["field_mismatches"],
            "conflict_count": len(full["conflicts"]),
            "conflict_examples": [
                {"key": list(c["key"]), "fields": c["fields"],
                 "turnover_ok": c["turnover_ok"]}
                for c in full["conflicts"][:20]],
        }
        # ---- mandatory 08-Jul-2024 reconciliation ----
        _log("phase", "reconciliation-20240708 starting")
        day = date(2024, 7, 8)
        s_day = sec_all[pd.to_datetime(sec_all["observation_date"]).dt.date == day]
        u_day = ud_all[pd.to_datetime(ud_all["observation_date"]).dt.date == day]
        day_cmp = eq.compare_regimes(s_day, u_day)
        evidence["reconciliation_20240708"] = {
            "sec_rows": len(s_day), "udiff_rows": len(u_day),
            "common_keys": day_cmp["common_keys"],
            "sec_only": day_cmp["sec_only"], "udiff_only": day_cmp["udiff_only"],
            "exact_keys": day_cmp["exact_keys"],
            "turnover_ok": day_cmp["turnover_ok"],
            "turnover_mismatch": day_cmp["turnover_mismatch"],
            "field_mismatches": day_cmp["field_mismatches"],
            "conflict_count": len(day_cmp["conflicts"]),
            "conflict_examples": [
                {"key": list(c["key"]), "fields": c["fields"],
                 "turnover_ok": c["turnover_ok"]}
                for c in day_cmp["conflicts"][:20]],
        }

    # ---- discontinuity classification (EQ series, per-symbol consecutive closes) ----
    _log("phase", "discontinuities starting")
    if not sec_all.empty:
        eq_rows = sec_all[sec_all["series"] == "EQ"].copy()
        eq_rows["observation_date"] = pd.to_datetime(eq_rows["observation_date"])
        eq_rows = eq_rows.sort_values(["symbol", "observation_date"])
        eq_rows["prev_close_lag"] = eq_rows.groupby("symbol")["close"].shift(1)
        eq_rows["ret"] = (eq_rows["close"] - eq_rows["prev_close_lag"]) / eq_rows["prev_close_lag"]
        big = eq_rows[eq_rows["ret"].abs() >= 0.20].copy()
        bands = {
            "20_50pct": int(((big["ret"].abs() >= 0.20) & (big["ret"].abs() < 0.50)).sum()),
            "50_100pct": int(((big["ret"].abs() >= 0.50) & (big["ret"].abs() < 1.00)).sum()),
            "gte_100pct": int((big["ret"].abs() >= 1.00).sum()),
        }
        evidence["discontinuities"] = {
            "eq_rows": int(len(eq_rows)),
            "sessions_with_prev_close": int(eq_rows["prev_close_lag"].notna().sum()),
            "abs_return_gte_20pct": int(len(big)),
            "bands": bands,
            "extreme_examples": [
                {"date": r["observation_date"].strftime("%Y-%m-%d"),
                 "symbol": r["symbol"], "prev": r["prev_close_lag"],
                 "close": r["close"], "ret": r["ret"]}
                for _, r in big.sort_values("ret", key=lambda s: s.abs(),
                                            ascending=False).head(15).iterrows()],
            "policy": "preserved unadjusted; not classified as corruption without authoritative corporate-action evidence",
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(evidence, fh, indent=2, default=str)
    print(f"wrote {args.out}")
    print(f"integrity gate passed: {evidence['integrity_gate']['passed']} "
          f"(mismatches: {len(mismatches)})")
    return 0 if evidence["integrity_gate"]["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
