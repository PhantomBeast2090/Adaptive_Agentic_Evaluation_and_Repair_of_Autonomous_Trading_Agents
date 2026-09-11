"""NIFTY 500 multi-file canonicalization.

Validates manually acquired annual NSE NIFTY 500 CSVs in place (raw files
are never rewritten) and builds a deduplicated canonical dataset under
``data/processed/india/market/``.

NSE observed format (UTF-8, no BOM, descending date order, RFC-4180
quoting, date format ``DD Mon YYYY``):
    "Index Name","Date","Open","High","Low","Close"

Unlike NIFTY 50, NSE supplies no Shares Traded / Turnover columns for
these exports; volume/turnover are therefore absent from the canonical
dataset and are never fabricated. Every row's Index Name was verified to
be ``NIFTY 500`` during the audit.

Canonical schema follows ``IndianIndexRecord`` (volume/turnover omitted):
    date, index_name, open, high, low, close, source, source_files

Invalid-row policy (documented, never silent): rows that fail numeric
parsing (including NSE ``-`` OHLC placeholders), OHLC consistency, or
positivity are EXCLUDED from the canonical dataset and recorded with
reasons. Raw evidence is untouched. Currently excluded: 04-Mar-1997,
03-Mar-1997, 21-Nov-1998 (``-`` OHLC placeholders); 30-Dec-2002,
14-May-2004, 27-Apr-2004, 18-May-2009, 29-Apr-2009 (impossible OHLC).
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

NSE_DATE_FORMAT = "%d %b %Y"
EXPECTED_INDEX_NAME = "NIFTY 500"
CANONICAL_COLUMNS = [
    "date",
    "index_name",
    "open",
    "high",
    "low",
    "close",
    "source",
    "source_files",
]


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_nifty500_raw_files(raw_dir: Path) -> List[Path]:
    """Return sorted annual NIFTY 500 CSVs. Raw files are never modified."""
    return sorted(raw_dir.glob("NIFTY 500_Historical_PR_*.csv"))


def normalize_nse_header(raw_header: List[str]) -> List[str]:
    """Strip whitespace from header fields without altering values."""
    return [part.strip() for part in raw_header]


def expected_nifty500_header() -> List[str]:
    return ["Index Name", "Date", "Open", "High", "Low", "Close"]


def header_matches_nifty500_schema(normalized: List[str]) -> bool:
    """Match the actual observed NSE NIFTY 500 header exactly."""
    return normalized == expected_nifty500_header()


def parse_nse_date(value: str) -> date:
    """Parse NSE 'DD Mon YYYY' dates (e.g. 01 Nov 2005). Raises on malformed."""
    text = value.strip()
    if not text:
        raise ValueError("empty date")
    return datetime.strptime(text, NSE_DATE_FORMAT).date()


@dataclass
class Nifty500ExcludedRow:
    source_file: str
    date_text: str
    reason: str


@dataclass
class Nifty500FileAudit:
    filename: str
    rel_path: str
    byte_size: int
    sha256: str
    header: List[str]
    header_valid: bool
    has_bom: bool
    index_names_observed: List[str]
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
    is_descending: bool
    is_ascending: bool
    first_observation: Optional[date]
    last_observation: Optional[date]


@dataclass
class Nifty500Overlap:
    overlap_date: date
    files: List[str]
    identical: bool
    records: List[Dict[str, Any]] = field(default_factory=list)


def _row_is_valid(
    o_val: float, h_val: float, l_val: float, c_val: float
) -> Optional[str]:
    """Return None if valid, else the exclusion reason. Never repairs."""
    if o_val <= 0 or h_val <= 0 or l_val <= 0 or c_val <= 0:
        return "non-positive price (OHLC must be > 0)"
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


def validate_nifty500_file(
    path: Path, rel_path: str
) -> Tuple[Nifty500FileAudit, pd.DataFrame, List[Nifty500ExcludedRow]]:
    """Validate one annual file in place.

    Returns (audit, valid-records frame, excluded rows with reasons).
    """
    raw_bytes = path.read_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()
    has_bom = raw_bytes[:3] == b"\xef\xbb\xbf"
    text = raw_bytes.decode("utf-8-sig")
    parsed = list(csv.reader(io.StringIO(text)))
    if not parsed:
        raise ValueError(f"{path.name}: empty file")
    header = normalize_nse_header(parsed[0])
    header_valid = header_matches_nifty500_schema(header)

    records: List[Dict[str, Any]] = []
    excluded: List[Nifty500ExcludedRow] = []
    index_names: List[str] = []
    null_malformed = 0
    numeric_failures = 0
    ohlc_violations = 0
    nonpositive = 0
    parsed_dates: List[date] = []
    seen: Dict[date, int] = {}

    for row in parsed[1:]:
        if len(row) != 6 or any(v.strip() == "" for v in row):
            null_malformed += 1
            continue
        name_text, date_text = row[0].strip(), row[1].strip()
        if name_text not in index_names:
            index_names.append(name_text)
        try:
            obs = parse_nse_date(date_text)
        except ValueError:
            null_malformed += 1
            continue
        if any(v.strip() == "-" for v in row[2:6]):
            numeric_failures += 1
            parsed_dates.append(obs)
            seen[obs] = seen.get(obs, 0) + 1
            excluded.append(
                Nifty500ExcludedRow(
                    source_file=path.name,
                    date_text=date_text,
                    reason="missing OHLC ('-' placeholder in source)",
                )
            )
            continue
        try:
            o_val = float(row[2].strip())
            h_val = float(row[3].strip())
            l_val = float(row[4].strip())
            c_val = float(row[5].strip())
        except ValueError:
            numeric_failures += 1
            continue
        parsed_dates.append(obs)
        seen[obs] = seen.get(obs, 0) + 1
        reason = _row_is_valid(o_val, h_val, l_val, c_val)
        if reason is not None:
            if "impossible OHLC" in reason:
                ohlc_violations += 1
            else:
                nonpositive += 1
            excluded.append(
                Nifty500ExcludedRow(
                    source_file=path.name, date_text=date_text, reason=reason
                )
            )
            continue
        records.append(
            {
                "date": obs,
                "index_name": name_text,
                "open": o_val,
                "high": h_val,
                "low": l_val,
                "close": c_val,
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
    audit = Nifty500FileAudit(
        filename=path.name,
        rel_path=rel_path,
        byte_size=len(raw_bytes),
        sha256=sha,
        header=header,
        header_valid=header_valid,
        has_bom=has_bom,
        index_names_observed=index_names,
        row_count=len(parsed) - 1,
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
        is_descending=is_desc,
        is_ascending=is_asc,
        first_observation=parsed_dates[0] if parsed_dates else None,
        last_observation=parsed_dates[-1] if parsed_dates else None,
    )
    frame = pd.DataFrame(records)
    return audit, frame, excluded


def audit_all_files(
    raw_dir: Path,
) -> Tuple[List[Nifty500FileAudit], List[pd.DataFrame], List[Nifty500ExcludedRow]]:
    files = discover_nifty500_raw_files(raw_dir)
    audits: List[Nifty500FileAudit] = []
    frames: List[pd.DataFrame] = []
    excluded_all: List[Nifty500ExcludedRow] = []
    for path in files:
        rel = f"data/raw/india/indices/{path.name}"
        audit, frame, excluded = validate_nifty500_file(path, rel)
        audits.append(audit)
        frames.append(frame)
        excluded_all.extend(excluded)
    return audits, frames, excluded_all


def detect_overlaps(
    frames: List[pd.DataFrame], filenames: List[str]
) -> List[Nifty500Overlap]:
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
            )
            by_date.setdefault(key, []).append((name, values))
    overlaps: List[Nifty500Overlap] = []
    for obs_date in sorted(by_date):
        entries = by_date[obs_date]
        if len(entries) <= 1:
            continue
        first_values = entries[0][1]
        identical = all(values == first_values for _, values in entries)
        overlaps.append(
            Nifty500Overlap(
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
    overlaps: List[Nifty500Overlap],
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
