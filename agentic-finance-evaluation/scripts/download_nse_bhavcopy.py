#!/usr/bin/env python3
"""Bulk-download official NSE Capital Market daily bhavcopy archives.

Two regimes (both verified live against official NSE endpoints):
  - sec_bhav  : https://archives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv
                earliest served: 2019-09-30; last: 2024-07-08
  - udiff     : https://archives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip
                earliest served: 2024-01-01; ongoing

Provenance rules (never violated):
  - Original NSE filenames are preserved byte-identically (zips stay zipped).
  - Every HTTP 200 artifact is verified: in-file observation date must be
    parsed; filename date != observation date is RECORDED, not assumed
    (the archive serves fallback-day content with HTTP 200, e.g. a Sunday
    request returning Friday's bhavcopy).
  - HTTP 404 is recorded as no-artifact (weekend/holiday/archive-limit are
    NOT distinguished here; classification belongs to validation).
  - A machine-readable index (bhavcopy_index.csv) carries URL, retrieval
    timestamp, sizes, SHA-256, and verification outcome per artifact.

Run from the project root, e.g.:
    python3 scripts/download_nse_bhavcopy.py --regime sec_bhav --start 2019-09-30 --end 2024-07-08
    python3 scripts/download_nse_bhavcopy.py --regime udiff --start 2024-01-01 --end 2026-09-11
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Research-Data-Acquisition"

SEC_BHAV_URL = (
    "https://archives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
)
UDIFF_URL = (
    "https://archives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{yyyymmdd}_F_0000.csv.zip"
)

INDEX_COLUMNS = [
    "filename",
    "regime",
    "requested_date",
    "infile_date",
    "date_match",
    "url",
    "retrieval_utc",
    "byte_size",
    "sha256",
    "http_status",
    "data_rows",
    "note",
]


def _fetch(url: str, timeout: int = 60) -> tuple[int, bytes]:
    """Fetch via curl (system cert store; this env's Python SSL store is broken)."""
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name
    try:
        proc = subprocess.run(
            ["curl", "-s", "--http1.1", "-A", UA, "--max-time", str(timeout),
             "-o", tmp_path, "-w", "%{http_code}", url],
            capture_output=True, timeout=timeout + 10,
        )
        try:
            status = int((proc.stdout or b"").decode().strip() or -1)
        except ValueError:
            status = -1
        payload = Path(tmp_path).read_bytes() if status == 200 else b""
        if status != 200:
            status = status if 100 <= status <= 599 else -1
        return status, payload
    except Exception as exc:  # network failure, not a server answer
        return -1, repr(exc).encode("utf-8", errors="replace")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _infile_date_sec_bhav(payload: bytes) -> tuple[str, int]:
    """Return (in-file DATE1 of first data row, data-row count)."""
    import urllib.error  # local import to keep module import-light

    text = payload.decode("utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return "", 0
    header = [c.strip() for c in lines[0].split(",")]
    try:
        date_idx = header.index("DATE1")
    except ValueError:
        return "", len(lines) - 1
    first = [c.strip() for c in lines[1].split(",")]
    infile = first[date_idx] if date_idx < len(first) else ""
    return infile, len(lines) - 1


def _infile_date_udiff(payload: bytes) -> tuple[str, int]:
    """Return (in-file TradDt of first data row, data-row count) without extracting."""
    import io
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not names:
                return "", 0
            with zf.open(names[0]) as fh:
                text = fh.read().decode("utf-8", errors="replace")
    except Exception:
        return "", 0
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return "", 0
    header = [c.strip() for c in lines[0].split(",")]
    try:
        date_idx = header.index("TradDt")
    except ValueError:
        return "", len(lines) - 1
    first = [c.strip() for c in lines[1].split(",")]
    infile = first[date_idx] if date_idx < len(first) else ""
    return infile, len(lines) - 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regime", choices=["sec_bhav", "udiff"], required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--raw-dir", type=Path,
                        default=Path("data/raw/india/equities"))
    parser.add_argument("--delay", type=float, default=0.4)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()

    raw_dir: Path = args.raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    # Per-regime index files: two concurrent sweeps must never share one
    # read-modify-write index (last finisher would clobber the other).
    # Merge with scripts/merge_bhavcopy_index.py after both sweeps finish.
    index_path = raw_dir / f"bhavcopy_index_{args.regime}.csv"

    existing: dict[str, dict[str, str]] = {}
    if index_path.exists():
        with open(index_path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                existing[row["filename"]] = row

    day = args.start
    fetched = skipped = failed = 0
    while day <= args.end:
        if day.weekday() < 5:  # weekends never published; sampled separately
            if args.regime == "sec_bhav":
                fname = f"sec_bhavdata_full_{day.strftime('%d%m%Y')}.csv"
                url = SEC_BHAV_URL.format(ddmmyyyy=day.strftime("%d%m%Y"))
            else:
                fname = f"BhavCopy_NSE_CM_0_0_0_{day.strftime('%Y%m%d')}_F_0000.csv.zip"
                url = UDIFF_URL.format(yyyymmdd=day.strftime("%Y%m%d"))
            target = raw_dir / fname
            if target.exists() and fname in existing and existing[fname].get("sha256"):
                skipped += 1
                day += timedelta(days=1)
                continue
            status, payload = -1, b""
            for attempt in range(args.retries):
                status, payload = _fetch(url)
                if status in (200, 404):
                    break
                time.sleep(2 * (attempt + 1))
            now = datetime.now(timezone.utc).isoformat()
            if status == 200 and payload:
                target.write_bytes(payload)
                sha = hashlib.sha256(payload).hexdigest()
                if args.regime == "sec_bhav":
                    infile, rows = _infile_date_sec_bhav(payload)
                else:
                    infile, rows = _infile_date_udiff(payload)
                requested = day.isoformat()
                # Normalize in-file date for comparison (regime formats differ).
                match = ""
                for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
                    try:
                        match = str(datetime.strptime(infile.strip(), fmt).date() == day)
                        break
                    except ValueError:
                        continue
                else:
                    match = f"UNPARSEABLE:{infile}"
                existing[fname] = {
                    "filename": fname, "regime": args.regime,
                    "requested_date": requested, "infile_date": infile,
                    "date_match": match, "url": url, "retrieval_utc": now,
                    "byte_size": str(len(payload)), "sha256": sha,
                    "http_status": str(status), "data_rows": str(rows),
                    "note": "" if match == "True" else "INFILE_DATE_DIFFERS_FROM_REQUEST",
                }
                fetched += 1
            else:
                existing[fname] = {
                    "filename": fname, "regime": args.regime,
                    "requested_date": day.isoformat(), "infile_date": "",
                    "date_match": "", "url": url, "retrieval_utc": now,
                    "byte_size": "0", "sha256": "",
                    "http_status": str(status), "data_rows": "0",
                    "note": "NO_ARTIFACT_SERVED",
                }
                failed += 1
            time.sleep(args.delay)
        day += timedelta(days=1)

    with open(index_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=INDEX_COLUMNS)
        writer.writeheader()
        for fname in sorted(existing):
            writer.writerow({k: existing[fname].get(k, "") for k in INDEX_COLUMNS})
    print(f"regime={args.regime} fetched={fetched} skipped={skipped} "
          f"no_artifact={failed} index={index_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
