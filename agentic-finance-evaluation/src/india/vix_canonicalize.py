"""India VIX multi-file canonicalization.

Validates manually acquired annual NSE India VIX CSVs in place (raw files
are never rewritten) and builds a deduplicated canonical dataset under
``data/processed/india/market/``.

NSE observed format (UTF-8 with BOM, ascending date order within file):
    Date ,Open ,High ,Low ,Close ,Prev. Close ,Change ,% Change

Note the sixth column is ``Prev. Close`` (with period), not ``Previous
Close`` as earlier adapter documentation assumed. The validator checks the
actual observed header.

Canonical schema follows ``IndianVIXRecord``:
    date, open, high, low, close, prev_close, change, pct_change,
    source, source_files

Invalid-row policy (documented, never silent): rows that parse but violate
OHLC consistency, positivity, or finiteness are EXCLUDED from the canonical
dataset and recorded with reasons. Raw evidence is untouched. Currently
excluded: 22-AUG-2013 (close < low) and 12-FEB-2021 / 30-MAR-2021
(zero-filled OHLC with NaN % Change placeholders).
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

NSE_DATE_FORMAT = "%d-%b-%Y"
CANONICAL_COLUMNS = [
    "date",
    "open",
    "high",
    "low",
    "close",
    "prev_close",
    "change",
    "pct_change",
    "source",
    "source_files",
]


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_vix_raw_files(raw_dir: Path) -> List[Path]:
    """Return sorted annual India VIX CSVs. Raw files are never modified."""
    return sorted(raw_dir.glob("hist_india_vix_*.csv"))


def normalize_nse_header(raw_header: str) -> List[str]:
    """Strip BOM/whitespace from header fields without altering values."""
    text = raw_header.lstrip("\ufeff")
    return [part.strip() for part in text.split(",")]


def expected_vix_header() -> List[str]:
    return [
        "Date",
        "Open",
        "High",
        "Low",
        "Close",
        "Prev. Close",
        "Change",
        "% Change",
    ]


def header_matches_vix_schema(normalized: List[str]) -> bool:
    """Match the actual observed NSE VIX header exactly after normalization."""
    return normalized == expected_vix_header()


def parse_nse_date(value: str) -> date:
    """Parse NSE 'DD-MMM-YYYY' dates (e.g. 03-NOV-2011). Raises on malformed."""
    text = value.strip()
    if not text:
        raise ValueError("empty date")
    return datetime.strptime(text, NSE_DATE_FORMAT).date()


@dataclass
class VixExcludedRow:
    source_file: str
    date_text: str
    reason: str


@dataclass
class VixFileAudit:
    filename: str
    rel_path: str
    byte_size: int
    sha256: str
    header: List[str]
    header_valid: bool
    row_count: int
    parsed_date_count: int
    valid_row_count: int
    excluded_row_count: int
    min_date: Optional[date]
    max_date: Optional[date]
    duplicate_dates_within_file: int
    null_or_malformed_rows: int
    numeric_parsing_failures: int
    ohlc_violations: int
    negative_or_nonpositive_count: int
    nonfinite_count: int
    change_consistency_failures: int
    is_descending: bool
    is_ascending: bool
    first_observation: Optional[date]
    last_observation: Optional[date]


@dataclass
class VixOverlap:
    overlap_date: date
    files: List[str]
    identical: bool
    records: List[Dict[str, Any]] = field(default_factory=list)


def _row_is_valid(
    o_val: float,
    h_val: float,
    l_val: float,
    c_val: float,
    pc_val: float,
    ch_val: float,
    pct_val: float,
) -> Optional[str]:
    """Return None if valid, else the exclusion reason. Never repairs."""
    for value in (o_val, h_val, l_val, c_val, pc_val, ch_val, pct_val):
        if not math.isfinite(value):
            return "non-finite value (inf or NaN)"
    if o_val <= 0 or h_val <= 0 or l_val <= 0 or c_val <= 0 or pc_val <= 0:
        return "non-positive price (OHLC/Prev. Close must be > 0)"
    if not (
        h_val >= o_val
        and h_val >= c_val
        and h_val >= l_val
        and l_val <= o_val
        and l_val <= c_val
        and h_val >= l_val
    ):
        return "impossible OHLC relationship"
    return None


def validate_vix_file(
    path: Path, rel_path: str
) -> Tuple[VixFileAudit, pd.DataFrame, List[VixExcludedRow]]:
    """Validate one annual file in place.

    Returns (audit, valid-records frame, excluded rows with reasons).
    """
    raw_bytes = path.read_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()
    text = raw_bytes.decode("utf-8-sig")
    lines = text.splitlines()
    if not lines:
        raise ValueError(f"{path.name}: empty file")
    header = normalize_nse_header(lines[0])
    header_valid = header_matches_vix_schema(header)

    records: List[Dict[str, Any]] = []
    excluded: List[VixExcludedRow] = []
    null_malformed = 0
    numeric_failures = 0
    ohlc_violations = 0
    nonpositive = 0
    nonfinite = 0
    change_failures = 0
    parsed_dates: List[date] = []
    valid_dates: List[date] = []
    seen: Dict[date, int] = {}

    for line in lines[1:]:
        if not line.strip():
            null_malformed += 1
            continue
        parts = line.split(",")
        if len(parts) != 8:
            null_malformed += 1
            continue
        fields = [p.strip() for p in parts]
        if any(v == "" for v in fields):
            null_malformed += 1
            continue
        date_text = fields[0]
        try:
            obs = parse_nse_date(date_text)
        except ValueError:
            null_malformed += 1
            continue
        try:
            o_val = float(fields[1])
            h_val = float(fields[2])
            l_val = float(fields[3])
            c_val = float(fields[4])
            pc_val = float(fields[5])
            ch_val = float(fields[6])
            pct_val = float(fields[7])
        except ValueError:
            numeric_failures += 1
            continue
        parsed_dates.append(obs)
        seen[obs] = seen.get(obs, 0) + 1
        reason = _row_is_valid(o_val, h_val, l_val, c_val, pc_val, ch_val, pct_val)
        if reason is not None:
            if "OHLC" in reason:
                ohlc_violations += 1
            if "non-positive" in reason:
                nonpositive += 1
            if "non-finite" in reason:
                nonfinite += 1
            excluded.append(
                VixExcludedRow(
                    source_file=path.name, date_text=date_text, reason=reason
                )
            )
            continue
        # Change / % Change cross-check (tolerance for NSE rounding only).
        if abs(ch_val - (c_val - pc_val)) > 0.011:
            change_failures += 1
        if pc_val != 0 and abs(pct_val - (c_val - pc_val) / pc_val * 100) > 0.011:
            change_failures += 1
        valid_dates.append(obs)
        records.append(
            {
                "date": obs,
                "open": o_val,
                "high": h_val,
                "low": l_val,
                "close": c_val,
                "prev_close": pc_val,
                "change": ch_val,
                "pct_change": pct_val,
                "source_file": path.name,
            }
        )

    dup_within = sum(count - 1 for count in seen.values() if count > 1)
    is_desc = (
        all(parsed_dates[i] >= parsed_dates[i + 1] for i in range(len(parsed_dates) - 1))
        if len(parsed_dates) > 1
        else True
    )
    is_asc = (
        all(parsed_dates[i] <= parsed_dates[i + 1] for i in range(len(parsed_dates) - 1))
        if len(parsed_dates) > 1
        else True
    )
    audit = VixFileAudit(
        filename=path.name,
        rel_path=rel_path,
        byte_size=len(raw_bytes),
        sha256=sha,
        header=header,
        header_valid=header_valid,
        row_count=len(lines) - 1,
        parsed_date_count=len(parsed_dates),
        valid_row_count=len(records),
        excluded_row_count=len(excluded),
        min_date=min(parsed_dates) if parsed_dates else None,
        max_date=max(parsed_dates) if parsed_dates else None,
        duplicate_dates_within_file=dup_within,
        null_or_malformed_rows=null_malformed,
        numeric_parsing_failures=numeric_failures,
        ohlc_violations=ohlc_violations,
        negative_or_nonpositive_count=nonpositive,
        nonfinite_count=nonfinite,
        change_consistency_failures=change_failures,
        is_descending=is_desc,
        is_ascending=is_asc,
        first_observation=parsed_dates[0] if parsed_dates else None,
        last_observation=parsed_dates[-1] if parsed_dates else None,
    )
    frame = pd.DataFrame(records)
    return audit, frame, excluded


def audit_all_files(
    raw_dir: Path,
) -> Tuple[List[VixFileAudit], List[pd.DataFrame], List[VixExcludedRow]]:
    files = discover_vix_raw_files(raw_dir)
    audits: List[VixFileAudit] = []
    frames: List[pd.DataFrame] = []
    excluded_all: List[VixExcludedRow] = []
    for path in files:
        rel = f"data/raw/india/india_vix/{path.name}"
        audit, frame, excluded = validate_vix_file(path, rel)
        audits.append(audit)
        frames.append(frame)
        excluded_all.extend(excluded)
    return audits, frames, excluded_all


def detect_overlaps(frames: List[pd.DataFrame], filenames: List[str]) -> List[VixOverlap]:
    """Group valid records by date across files; flag identical vs conflicting."""
    by_date: Dict[date, List[Tuple[str, Tuple[float, ...]]]] = {}
    for frame, name in zip(frames, filenames):
        for _, row in frame.iterrows():
            key = row["date"] if isinstance(row["date"], date) else pd.to_datetime(row["date"]).date()
            values = (
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                float(row["prev_close"]),
                float(row["change"]),
                float(row["pct_change"]),
            )
            by_date.setdefault(key, []).append((name, values))
    overlaps: List[VixOverlap] = []
    for obs_date in sorted(by_date):
        entries = by_date[obs_date]
        if len(entries) <= 1:
            continue
        first_values = entries[0][1]
        identical = all(values == first_values for _, values in entries)
        overlaps.append(
            VixOverlap(
                overlap_date=obs_date,
                files=[name for name, _ in entries],
                identical=identical,
                records=[
                    {"source_file": name, "values": list(values)}
                    for name, values in entries
                ],
            )
        )
    return overlaps


def build_canonical(
    frames: List[pd.DataFrame],
    filenames: List[str],
    overlaps: List[VixOverlap],
) -> pd.DataFrame:
    """Combine validated frames, dedup only proven identical boundary dates.

    Raises ValueError if any conflicting overlap exists — the caller must
    report the conflict rather than choosing a record arbitrarily.
    """
    conflicts = [item for item in overlaps if not item.identical]
    if conflicts:
        detail = "; ".join(
            f"{item.overlap_date} in {item.files}" for item in conflicts[:5]
        )
        raise ValueError(f"Conflicting overlapping records detected: {detail}")
    combined = pd.concat(frames, ignore_index=True)
    # Provenance: every raw file that carried this observation date.
    provenance: Dict[date, List[str]] = {}
    for frame, name in zip(frames, filenames):
        for value in frame["date"].tolist():
            key = value if isinstance(value, date) else pd.to_datetime(value).date()
            provenance.setdefault(key, [])
            if name not in provenance[key]:
                provenance[key].append(name)
    # Deduplicate identical boundary observations: keep first occurrence,
    # sorted ascending by date, never forward-fill or fabricate.
    combined["_sort_date"] = pd.to_datetime(combined["date"])
    combined = combined.sort_values("_sort_date").drop_duplicates(
        subset=["date"], keep="first"
    )
    combined["source_files"] = combined["date"].map(
        lambda d: ";".join(
            sorted(provenance[d if isinstance(d, date) else pd.to_datetime(d).date()])
        )
    )
    combined["date"] = pd.to_datetime(combined["date"]).dt.date
    combined["source"] = "NSE"
    combined = combined.sort_values("date").reset_index(drop=True)
    return combined[CANONICAL_COLUMNS]
