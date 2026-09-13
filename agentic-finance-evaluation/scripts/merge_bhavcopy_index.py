#!/usr/bin/env python3
"""Merge per-regime bhavcopy acquisition indexes into bhavcopy_index.csv.

Run after both download sweeps finish. Fails if either per-regime index
is missing.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

COLUMNS = [
    "filename", "regime", "requested_date", "infile_date", "date_match",
    "url", "retrieval_utc", "byte_size", "sha256", "http_status",
    "data_rows", "note",
]


def main() -> int:
    raw_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/raw/india/equities")
    parts = [raw_dir / "bhavcopy_index_sec_bhav.csv",
             raw_dir / "bhavcopy_index_udiff.csv"]
    for part in parts:
        if not part.exists():
            print(f"MISSING: {part} — run both download sweeps first.")
            return 1
    merged: dict[str, dict[str, str]] = {}
    for part in parts:
        with open(part, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                merged[row["filename"]] = {k: row.get(k, "") for k in COLUMNS}
    out = raw_dir / "bhavcopy_index.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for fname in sorted(merged):
            writer.writerow(merged[fname])
    print(f"merged {len(merged)} entries -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
