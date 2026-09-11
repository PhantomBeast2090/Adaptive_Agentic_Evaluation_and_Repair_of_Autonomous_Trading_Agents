"""RBI USD/INR reference-rate canonicalization.

Validates the manually acquired RBI Reference Rate Archive export in place
(raw file is never rewritten) and builds a canonical dataset under
``data/processed/india/market/``.

Raw evidence: a single ``.xls`` file that is actually an HTML table export
(ASP.NET GridView format, starts with ``<style>``), parsed here with the
standard library only — no new dependencies. Observed structure: one
table, first row header, two columns:

    Date | USD (INR / 1 USD)

Dates are ``DD/MM/YYYY``; the single rate column is INR per 1 USD, i.e.
the official RBI USD/INR reference rate. No multi-field ambiguity exists
in this artifact (no separate buying/selling/spot columns); the filename
(``BankWise.xls``) is preserved as supplied but content determines
semantics. File order is descending by date.

Canonical schema follows ``IndianCurrencyRecord``:
    date, rate, source, is_reference_rate, source_files

Source coverage limitation (documented, never filled): the export holds
1998-08-25 to 2026-09-11 with 2019/2020/2021 entirely absent and a
1358-day gap 2018-07-24 -> 2022-04-12. Missing observations are never
interpolated or forward-filled.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

NSE_DATE_FORMAT = "%d/%m/%Y"
EXPECTED_RATE_HEADER = "USD (INR / 1 USD)"
CANONICAL_COLUMNS = [
    "date",
    "rate",
    "source",
    "is_reference_rate",
    "source_files",
]


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_usdinr_raw_files(raw_dir: Path) -> List[Path]:
    """Return sorted RBI USD/INR raw files. Raw files are never modified."""
    return sorted(raw_dir.glob("*.xls"))


class _TableParser(HTMLParser):
    """Extract the first HTML table as rows of cell text (stdlib only)."""

    def __init__(self) -> None:
        super().__init__()
        self._in_table = False
        self._in_cell = False
        self._current_row: List[str] = []
        self._current_cell: List[str] = []
        self.rows: List[List[str]] = []
        self._done = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        if tag == "table" and not self.rows and not self._in_table:
            self._in_table = True
        elif self._in_table and tag == "tr":
            self._current_row = []
        elif self._in_table and tag in ("td", "th"):
            self._in_cell = True
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "table" and self._in_table:
            self._in_table = False
            self._done = True
        elif self._in_table and tag in ("td", "th") and self._in_cell:
            self._in_cell = False
            self._current_row.append("".join(self._current_cell).strip())
        elif self._in_table and tag == "tr":
            if self._current_row:
                self.rows.append(self._current_row)

    def handle_data(self, data: str) -> None:
        if self._in_table and self._in_cell and not self._done:
            self._current_cell.append(data)


def read_rbi_table(path: Path) -> List[List[str]]:
    """Read the first HTML table from the RBI export without modifying it."""
    parser = _TableParser()
    parser.feed(path.read_bytes().decode("utf-8", errors="replace"))
    return parser.rows


def normalize_header(cells: List[str]) -> List[str]:
    """Strip whitespace from header cells without altering values."""
    return [cell.strip() for cell in cells]


def expected_usdinr_header() -> List[str]:
    return ["Date", EXPECTED_RATE_HEADER]


def header_matches_usdinr_schema(normalized: List[str]) -> bool:
    """Match the actual observed RBI header exactly after normalization."""
    return normalized == expected_usdinr_header()


def parse_rbi_date(value: str) -> date:
    """Parse RBI 'DD/MM/YYYY' dates (e.g. 11/09/2026). Raises on malformed."""
    text = value.strip()
    if not text:
        raise ValueError("empty date")
    return datetime.strptime(text, NSE_DATE_FORMAT).date()


@dataclass
class UsdInrExcludedRow:
    source_file: str
    date_text: str
    reason: str


@dataclass
class UsdInrFileAudit:
    filename: str
    rel_path: str
    byte_size: int
    sha256: str
    container_format: str
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
    nonpositive_count: int
    is_descending: bool
    is_ascending: bool
    first_observation: Optional[date]
    last_observation: Optional[date]


@dataclass
class UsdInrOverlap:
    overlap_date: date
    files: List[str]
    identical: bool
    records: List[Dict[str, Any]] = field(default_factory=list)


def validate_usdinr_file(
    path: Path, rel_path: str
) -> Tuple[UsdInrFileAudit, pd.DataFrame, List[UsdInrExcludedRow]]:
    """Validate one RBI export in place.

    Returns (audit, valid-records frame, excluded rows with reasons).
    """
    raw_bytes = path.read_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()
    rows = read_rbi_table(path)
    if not rows:
        raise ValueError(f"{path.name}: no HTML table found")
    header = normalize_header(rows[0])
    header_valid = header_matches_usdinr_schema(header)
    data_rows = rows[1:]

    records: List[Dict[str, Any]] = []
    excluded: List[UsdInrExcludedRow] = []
    null_malformed = 0
    numeric_failures = 0
    nonpositive = 0
    parsed_dates: List[date] = []
    seen: Dict[date, int] = {}

    for row in data_rows:
        if len(row) != 2 or any(v.strip() == "" for v in row):
            null_malformed += 1
            continue
        date_text, rate_text = row[0].strip(), row[1].strip()
        try:
            obs = parse_rbi_date(date_text)
        except ValueError:
            null_malformed += 1
            continue
        try:
            rate_val = float(rate_text.replace(",", ""))
        except ValueError:
            numeric_failures += 1
            continue
        parsed_dates.append(obs)
        seen[obs] = seen.get(obs, 0) + 1
        if not rate_val > 0:
            nonpositive += 1
            excluded.append(
                UsdInrExcludedRow(
                    source_file=path.name,
                    date_text=date_text,
                    reason="non-positive rate (INR per USD must be > 0)",
                )
            )
            continue
        records.append(
            {
                "date": obs,
                "rate": rate_val,
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
    audit = UsdInrFileAudit(
        filename=path.name,
        rel_path=rel_path,
        byte_size=len(raw_bytes),
        sha256=sha,
        container_format="HTML table exported as .xls (ASP.NET GridView)",
        header=header,
        header_valid=header_valid,
        row_count=len(data_rows),
        parsed_date_count=len(parsed_dates),
        valid_row_count=len(records),
        excluded_row_count=len(excluded),
        min_date=min(parsed_dates) if parsed_dates else None,
        max_date=max(parsed_dates) if parsed_dates else None,
        duplicate_dates_within_file=dup_within,
        null_or_malformed_rows=null_malformed,
        numeric_parsing_failures=numeric_failures,
        nonpositive_count=nonpositive,
        is_descending=is_desc,
        is_ascending=is_asc,
        first_observation=parsed_dates[0] if parsed_dates else None,
        last_observation=parsed_dates[-1] if parsed_dates else None,
    )
    frame = pd.DataFrame(records)
    return audit, frame, excluded


def audit_all_files(
    raw_dir: Path,
) -> Tuple[List[UsdInrFileAudit], List[pd.DataFrame], List[UsdInrExcludedRow]]:
    files = discover_usdinr_raw_files(raw_dir)
    audits: List[UsdInrFileAudit] = []
    frames: List[pd.DataFrame] = []
    excluded_all: List[UsdInrExcludedRow] = []
    for path in files:
        rel = f"data/raw/india/currency/{path.name}"
        audit, frame, excluded = validate_usdinr_file(path, rel)
        audits.append(audit)
        frames.append(frame)
        excluded_all.extend(excluded)
    return audits, frames, excluded_all


def detect_overlaps(
    frames: List[pd.DataFrame], filenames: List[str]
) -> List[UsdInrOverlap]:
    """Group valid records by date across files; flag identical vs conflicting."""
    by_date: Dict[date, List[Tuple[str, float]]] = {}
    for frame, name in zip(frames, filenames):
        for _, row in frame.iterrows():
            key = row["date"] if isinstance(row["date"], date) else pd.to_datetime(row["date"]).date()
            by_date.setdefault(key, []).append((name, float(row["rate"])))
    overlaps: List[UsdInrOverlap] = []
    for obs_date in sorted(by_date):
        entries = by_date[obs_date]
        if len(entries) <= 1:
            continue
        first_value = entries[0][1]
        identical = all(value == first_value for _, value in entries)
        overlaps.append(
            UsdInrOverlap(
                overlap_date=obs_date,
                files=[name for name, _ in entries],
                identical=identical,
                records=[
                    {"source_file": name, "values": [value]}
                    for name, value in entries
                ],
            )
        )
    return overlaps


def build_canonical(
    frames: List[pd.DataFrame],
    filenames: List[str],
    overlaps: List[UsdInrOverlap],
) -> pd.DataFrame:
    """Combine validated frames, dedup only proven identical dates.

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
    # Deduplicate identical observations: keep first occurrence, sorted
    # ascending by date, never forward-fill or fabricate.
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
    combined["source"] = "RBI_REFERENCE_RATE"
    combined["is_reference_rate"] = True
    combined = combined.sort_values("date").reset_index(drop=True)
    return combined[CANONICAL_COLUMNS]
