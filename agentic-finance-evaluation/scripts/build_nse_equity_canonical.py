#!/usr/bin/env python3
"""Deterministically build the canonical NSE equity daily dataset.

Reads validated raw artifacts (both regimes) plus the acquisition index,
runs the full pipeline from src/india/nse_equity_canonicalize.py, and
writes data/processed/india/equities/nse_equity_daily.csv.

Identical raw inputs produce byte-identical output (no timestamps, no
random IDs in canonical data). Prints row counts and SHA-256.

Usage (project root):
    PYTHONPATH=. python3 scripts/build_nse_equity_canonical.py
"""

from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path

import pandas as pd

# Archive-integrity exclusion (qualitative finding, documented in manifest):
# NSE deterministically serves 27-Jun-2019 content for 30-Sep-2019 requests
# (byte-identical on redownload). Filename/content contradict, so the date
# is unresolvable: fail closed, exclude the file, preserve it in raw.
EXCLUDE_FILES = ["sec_bhavdata_full_30092019.csv"]


def main() -> int:
    sys.path.insert(0, ".")
    from src.india import nse_equity_canonicalize as eq

    raw_dir = Path("data/raw/india/equities")
    out_path = Path("data/processed/india/equities/nse_equity_daily.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    index_dates: dict[str, str] = {}
    with open(raw_dir / "bhavcopy_index.csv", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("http_status") == "200":
                index_dates[row["filename"]] = row.get("requested_date", "")

    sec_files, udiff_files = eq.discover_raw_files(raw_dir)
    sec_frames: list[pd.DataFrame] = []
    sec_names: list[str] = []
    for path in sec_files:
        rel = f"data/raw/india/equities/{path.name}"
        _, frame, _ = eq.validate_sec_bhav_file(
            path, rel, index_dates.get(path.name) or None)
        sec_frames.append(frame)
        sec_names.append(path.name)
    udiff_frames: list[pd.DataFrame] = []
    udiff_names: list[str] = []
    for path in udiff_files:
        rel = f"data/raw/india/equities/{path.name}"
        _, frame, _ = eq.validate_udiff_file(
            path, rel, index_dates.get(path.name) or None)
        udiff_frames.append(frame)
        udiff_names.append(path.name)

    import pandas as _pd
    sec_all = _pd.concat(sec_frames, ignore_index=True)
    ud_all = _pd.concat(udiff_frames, ignore_index=True)
    cmp_all = eq.compare_regimes(sec_all, ud_all)
    blocking = [tuple(c["key"]) for c in cmp_all.get("conflicts", []) if c["fields"]]
    if blocking:
        # Evidence-derived exclusion: both official regimes publish
        # different values for these keys; neither is provably wrong.
        # Exclude with manifest accounting (never silently resolved).
        print(f"excluding {len(blocking)} cross-regime conflict keys:")
        for key in blocking:
            print(f"  {key}")
    print(f"excluding {len(EXCLUDE_FILES)} mislabeled files: {EXCLUDE_FILES}")
    canonical, stats = eq.build_canonical(
        sec_frames, sec_names, udiff_frames or None, udiff_names or None,
        exclude_files=EXCLUDE_FILES, exclude_keys=blocking)
    canonical.to_csv(out_path, index=False)
    sha = hashlib.sha256(out_path.read_bytes()).hexdigest()
    print(f"sec_files={len(sec_files)} udiff_files={len(udiff_files)} "
          f"rows={len(canonical)} "
          f"dates={canonical['observation_date'].nunique()} "
          f"keys={(canonical['observation_date'].astype(str) + '|' + canonical['symbol'] + '|' + canonical['series']).nunique()}")
    print(f"isin matched={stats['isin_attach']['matched']} "
          f"unmatched={stats['isin_attach']['unmatched']} "
          f"ambiguous={stats['isin_attach']['ambiguous']}")
    print(f"wrote {out_path} sha256={sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
