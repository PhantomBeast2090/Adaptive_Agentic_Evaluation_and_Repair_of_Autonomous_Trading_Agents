"""NIFTY 50 multi-file canonicalization.

Validates manually acquired annual NSE index CSVs in place (raw files are
never rewritten) and builds a deduplicated canonical dataset under
``data/processed/india/market/``.

NSE observed format (UTF-8 with BOM, descending date order):
    Date ,Open ,High ,Low ,Close ,Shares Traded ,Turnover (Rs. Cr / ₹ Cr)

Canonical schema follows ``IndianIndexRecord``:
    date, index_name, open, high, low, close, volume, turnover,
    source, source_files
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

NSE_DATE_FORMAT = "%d-%b-%Y"
CANONICAL_COLUMNS = [
    "date",
    "index_name",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "turnover",
    "source",
    "source_files",
]


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_nifty_raw_files(raw_dir: Path) -> List[Path]:
    """Return sorted annual NIFTY 50 CSVs. Raw files are never modified."""
    return sorted(raw_dir.glob("NIFTY 50-*.csv"))


def normalize_nse_header(raw_header: str) -> List[str]:
    """Strip BOM/whitespace from header fields without altering values."""
    text = raw_header.lstrip("\ufeff")
    return [part.strip() for part in text.split(",")]


def expected_nse_header() -> List[str]:
    return [
        "Date",
        "Open",
        "High",
        "Low",
        "Close",
        "Shares Traded",
        "Turnover (₹ Cr)",
    ]


def header_matches_nse_schema(normalized: List[str]) -> bool:
    """Accept both 'Turnover (₹ Cr)' and legacy 'Turnover (Rs. Cr)' variants."""
    if len(normalized) != 7:
        return False
    if normalized[:6] != ["Date", "Open", "High", "Low", "Close", "Shares Traded"]:
        return False
    turnover = normalized[6]
    return turnover in {"Turnover (₹ Cr)", "Turnover (Rs. Cr)"}


def parse_nse_date(value: str) -> date:
    """Parse NSE 'DD-MMM-YYYY' dates (e.g. 03-NOV-1999). Raises on malformed."""
    text = value.strip()
    if not text:
        raise ValueError("empty date")
    return datetime.strptime(text, NSE_DATE_FORMAT).date()


@dataclass
class NiftyFileAudit:
    filename: str
    rel_path: str
    byte_size: int
    sha256: str
    header: List[str]
    header_valid: bool
    row_count: int
    parsed_date_count: int
    min_date: Optional[date]
    max_date: Optional[date]
    duplicate_dates_within_file: int
    null_or_malformed_rows: int
    numeric_parsing_failures: int
    ohlc_violations: int
    negative_price_count: int
    negative_volume_count: int
    negative_turnover_count: int
    is_descending: bool
    is_ascending: bool
    first_observation: Optional[date]
    last_observation: Optional[date]


@dataclass
class NiftyOverlap:
    overlap_date: date
    files: List[str]
    identical: bool
    records: List[Dict[str, Any]] = field(default_factory=list)


def validate_nse_file(path: Path, rel_path: str) -> Tuple[NiftyFileAudit, pd.DataFrame]:
    """Validate one annual file in place. Returns audit + parsed records frame."""
    raw_bytes = path.read_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()
    text = raw_bytes.decode("utf-8-sig")
    lines = text.splitlines()
    if not lines:
        raise ValueError(f"{path.name}: empty file")
    header = normalize_nse_header(lines[0])
    header_valid = header_matches_nse_schema(header)

    records: List[Dict[str, Any]] = []
    null_malformed = 0
    numeric_failures = 0
    ohlc_violations = 0
    neg_price = 0
    neg_vol = 0
    neg_turn = 0
    parsed_dates: List[date] = []
    seen: Dict[date, int] = {}

    for line in lines[1:]:
        if not line.strip():
            null_malformed += 1
            continue
        parts = line.split(",")
        if len(parts) != 7:
            null_malformed += 1
            continue
        fields = [p.strip() for p in parts]
        if any(v == "" for v in fields):
            null_malformed += 1
            continue
        date_text, o_text, h_text, l_text, c_text, sh_text, to_text = fields
        try:
            obs = parse_nse_date(date_text)
        except ValueError:
            null_malformed += 1
            continue
        try:
            o_val = float(o_text)
            h_val = float(h_text)
            l_val = float(l_text)
            c_val = float(c_text)
            sh_val = float(sh_text)
            to_val = float(to_text)
        except ValueError:
            numeric_failures += 1
            continue
        parsed_dates.append(obs)
        seen[obs] = seen.get(obs, 0) + 1
        if o_val <= 0 or h_val <= 0 or l_val <= 0 or c_val <= 0:
            neg_price += 1
        if sh_val < 0:
            neg_vol += 1
        if to_val < 0:
            neg_turn += 1
        # Impossible OHLC: high must dominate, low must be dominated.
        if not (
            h_val >= o_val
            and h_val >= c_val
            and h_val >= l_val
            and l_val <= o_val
            and l_val <= c_val
            and h_val >= l_val
        ):
            ohlc_violations += 1
        records.append(
            {
                "date": obs,
                "open": o_val,
                "high": h_val,
                "low": l_val,
                "close": c_val,
                "volume": sh_val,
                "turnover": to_val,
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
    audit = NiftyFileAudit(
        filename=path.name,
        rel_path=rel_path,
        byte_size=len(raw_bytes),
        sha256=sha,
        header=header,
        header_valid=header_valid,
        row_count=len(lines) - 1,
        parsed_date_count=len(parsed_dates),
        min_date=min(parsed_dates) if parsed_dates else None,
        max_date=max(parsed_dates) if parsed_dates else None,
        duplicate_dates_within_file=dup_within,
        null_or_malformed_rows=null_malformed,
        numeric_parsing_failures=numeric_failures,
        ohlc_violations=ohlc_violations,
        negative_price_count=neg_price,
        negative_volume_count=neg_vol,
        negative_turnover_count=neg_turn,
        is_descending=is_desc,
        is_ascending=is_asc,
        first_observation=parsed_dates[0] if parsed_dates else None,
        last_observation=parsed_dates[-1] if parsed_dates else None,
    )
    frame = pd.DataFrame(records)
    return audit, frame


def audit_all_files(raw_dir: Path) -> Tuple[List[NiftyFileAudit], List[pd.DataFrame]]:
    files = discover_nifty_raw_files(raw_dir)
    audits: List[NiftyFileAudit] = []
    frames: List[pd.DataFrame] = []
    for path in files:
        rel = f"data/raw/india/indices/{path.name}"
        audit, frame = validate_nse_file(path, rel)
        audits.append(audit)
        frames.append(frame)
    return audits, frames


def detect_overlaps(frames: List[pd.DataFrame], filenames: List[str]) -> List[NiftyOverlap]:
    """Group records by date across files; flag identical vs conflicting."""
    by_date: Dict[date, List[Tuple[str, Tuple[float, ...]]]] = {}
    for frame, name in zip(frames, filenames):
        for _, row in frame.iterrows():
            key = row["date"] if isinstance(row["date"], date) else pd.to_datetime(row["date"]).date()
            values = (
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                float(row["volume"]),
                float(row["turnover"]),
            )
            by_date.setdefault(key, []).append((name, values))
    overlaps: List[NiftyOverlap] = []
    for obs_date in sorted(by_date):
        entries = by_date[obs_date]
        if len(entries) <= 1:
            continue
        first_values = entries[0][1]
        identical = all(values == first_values for _, values in entries)
        overlaps.append(
            NiftyOverlap(
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
    overlaps: List[NiftyOverlap],
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
    combined["index_name"] = "NIFTY 50"
    combined["source"] = "NSE"
    combined = combined.sort_values("date").reset_index(drop=True)
    return combined[CANONICAL_COLUMNS]
