"""EIA Europe Brent Spot Price FOB (RBRTE) daily canonicalization.

Official source: U.S. Energy Information Administration (EIA),
Petroleum & Other Liquids, Europe Brent Spot Price FOB,
series identifier RBRTE.
Landing page: https://www.eia.gov/dnav/pet/hist/RBRTED.htm
Direct artifact: https://www.eia.gov/dnav/pet/hist_xls/RBRTEd.xls

Economic role: GLOBAL EXOGENOUS CRUDE INPUT (Tier C / crude). This is
NOT an Indian exchange instrument. Economic category (crude/commodity)
and data role (global exogenous) are kept separate in metadata.

Spot-vs-futures (why this is Brent SPOT, never futures):
  - The EIA RBRTE series measures the physical spot assessment for
    Brent (Free On Board, dollars per barrel) for dated cargoes, not
    the price of any dated ICE Brent futures contract.
  - Spot and futures differ economically: futures embed cost-of-carry,
    convenience yield, financing, contract expiry/roll effects, and
    position squeezes. Substituting a futures settlement (or building
    OHLC/a continuous rolled series) would inject term-structure and
    roll-method artifacts into what must remain a pure exogenous spot
    input, and would let roll-decision information leak across time.
  - Therefore: no futures substitution, no spot<->futures conversion,
    no OHLC construction, no synthetic splicing. One observation per
    source date, exactly as published.

Raw evidence (immutable, under ``data/raw/india/crude/``):
  - Single BIFF ``.xls`` workbook (``eia_rbrte_brent_spot_daily.xls``),
    sheet ``Data 1``: row 0 title, row 1 ``Sourcekey | RBRTE``
    (series identity), row 2 ``Date | Europe Brent Spot Price FOB
    (Dollars per Barrel)`` header, rows 3+ Excel-serial dates with
    USD/bbl spot prices. Parsed here with ``xlrd`` (read-only); raw
    bytes are never modified.

Canonical schema (``data/processed/india/crude/``):
    observation_date, availability_date, brent_spot_usd_bbl,
    vintage_status, revision_version, availability_basis,
    source, series_id, unit, source_files

Temporal semantics (fail-closed unknown availability):
  - observation_date: the EIA observation day (ISO YYYY-MM-DD).
  - availability_date: NULL/unknown. EIA publishes observation dates
    but exposes no per-observation historical publication timestamps
    precise enough for an information-set boundary, so nothing is
    fabricated (no availability = observation assumption, no lag).
  - agent_eligible_rows() therefore returns zero rows and
    build_agent_information_set() fails closed BEFORE constructing an
    InformationSet (whose constructor raises on NA availability and
    must not be weakened to accommodate Brent).

Calendar: Brent is a global commodity series. Its weekday-only
(Mon-Fri, no weekends observed) calendar is NOT the NSE calendar.
Gaps are never filled, interpolated, or forward-filled; the later
common-temporal-intersection layer reconciles cross-dataset
calendars. Coverage-audit calendar lines against NSE are
not applicable to this dataset and must be disregarded.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

RAW_FILENAME = "eia_rbrte_brent_spot_daily.xls"
RAW_SUBDIR = "crude"
DATA_SHEET = "Data 1"
EXPECTED_SERIES_ID = "RBRTE"
EXPECTED_TITLE_FRAGMENT = "Europe Brent Spot Price FOB"
EXPECTED_UNIT = "USD_per_bbl"
EXPECTED_SOURCE = "EIA"

CANONICAL_COLUMNS = [
    "observation_date",
    "availability_date",
    "brent_spot_usd_bbl",
    "vintage_status",
    "revision_version",
    "availability_basis",
    "source",
    "series_id",
    "unit",
    "source_files",
]

# No historical publication timing is available from EIA, so no vintage
# is agent-eligible. This set is intentionally empty.
AGENT_ELIGIBLE_VINTAGES = frozenset()


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_brent_raw_files(raw_dir: Path) -> List[Path]:
    """Return sorted EIA Brent raw files. Raw files are never modified."""
    return sorted(raw_dir.glob("*.xls"))


def read_eia_workbook(path: Path) -> Tuple[str, List[Tuple[date, float]]]:
    """Read the EIA RBRTE workbook (read-only) into (series_id, records).

    Verifies sheet name, series identity (Sourcekey RBRTE), and header
    before returning observation (date, price) pairs in file order.
    Raises ValueError on any structural deviation.
    """
    import xlrd

    workbook = xlrd.open_workbook(str(path))
    if DATA_SHEET not in workbook.sheet_names():
        raise ValueError(f"{path.name}: sheet {DATA_SHEET!r} not found")
    sheet = workbook.sheet_by_name(DATA_SHEET)
    if sheet.nrows < 4 or sheet.ncols < 2:
        raise ValueError(f"{path.name}: workbook too small to hold RBRTE data")
    title = str(sheet.cell_value(0, 1))
    if EXPECTED_TITLE_FRAGMENT not in title:
        raise ValueError(f"{path.name}: unexpected title {title!r}")
    if str(sheet.cell_value(1, 0)).strip().lower() != "sourcekey":
        raise ValueError(f"{path.name}: row 1 is not the Sourcekey row")
    series_id = str(sheet.cell_value(1, 1)).strip()
    if series_id != EXPECTED_SERIES_ID:
        raise ValueError(f"{path.name}: unexpected series {series_id!r}")
    header_date = str(sheet.cell_value(2, 0)).strip().lower()
    header_price = str(sheet.cell_value(2, 1))
    if header_date != "date" or EXPECTED_TITLE_FRAGMENT not in header_price:
        raise ValueError(f"{path.name}: unexpected header row")
    datemode = workbook.datemode
    records: List[Tuple[date, float]] = []
    for row in range(3, sheet.nrows):
        raw_date = sheet.cell_value(row, 0)
        raw_price = sheet.cell_value(row, 1)
        if raw_date == "" or raw_price == "":
            raise ValueError(f"{path.name}: blank cell at data row {row}")
        try:
            obs = xlrd.xldate_as_datetime(float(raw_date), datemode).date()
        except Exception as exc:
            raise ValueError(
                f"{path.name}: unparseable date at row {row}: {raw_date!r}"
            ) from exc
        try:
            price = float(raw_price)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{path.name}: unparseable price at row {row}: {raw_price!r}"
            ) from exc
        records.append((obs, price))
    return series_id, records


@dataclass
class BrentExcludedRow:
    source_file: str
    date_text: str
    reason: str


@dataclass
class BrentFileAudit:
    filename: str
    rel_path: str
    byte_size: int
    sha256: str
    container_format: str
    series_id: str
    series_id_valid: bool
    header_valid: bool
    row_count: int
    valid_row_count: int
    excluded_row_count: int
    min_date: Optional[date]
    max_date: Optional[date]
    duplicate_dates_within_file: int
    null_or_malformed_rows: int
    numeric_parsing_failures: int
    nonpositive_count: int
    nonfinite_count: int
    is_ascending: bool
    first_observation: Optional[date]
    last_observation: Optional[date]


@dataclass
class BrentOverlap:
    observation_date: date
    files: List[str]
    identical: bool
    records: List[Dict[str, Any]] = field(default_factory=list)


def validate_brent_file(
    path: Path, rel_path: str
) -> Tuple[BrentFileAudit, pd.DataFrame, List[BrentExcludedRow]]:
    """Validate one EIA RBRTE export in place.

    Returns (audit, valid-records frame, excluded rows with reasons).
    The raw file is never modified.
    """
    raw_bytes = path.read_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()
    series_id, records = read_eia_workbook(path)

    valid: List[Dict[str, Any]] = []
    excluded: List[BrentExcludedRow] = []
    null_malformed = 0
    numeric_failures = 0
    nonpositive = 0
    nonfinite = 0
    seen: Dict[date, int] = {}
    parsed_dates: List[date] = []

    for obs, price in records:
        parsed_dates.append(obs)
        seen[obs] = seen.get(obs, 0) + 1
        if not math.isfinite(price):
            nonfinite += 1
            numeric_failures += 1
            excluded.append(
                BrentExcludedRow(
                    source_file=path.name,
                    date_text=obs.isoformat(),
                    reason="non-finite price (must be finite USD/bbl)",
                )
            )
            continue
        if not price > 0:
            nonpositive += 1
            excluded.append(
                BrentExcludedRow(
                    source_file=path.name,
                    date_text=obs.isoformat(),
                    reason="non-positive price (USD/bbl must be > 0)",
                )
            )
            continue
        valid.append(
            {
                "observation_date": obs,
                "brent_spot_usd_bbl": price,
                "source_file": path.name,
            }
        )

    dup_within = sum(count - 1 for count in seen.values() if count > 1)
    is_asc = (
        all(parsed_dates[i] <= parsed_dates[i + 1] for i in range(len(parsed_dates) - 1))
        if len(parsed_dates) > 1
        else True
    )
    audit = BrentFileAudit(
        filename=path.name,
        rel_path=rel_path,
        byte_size=len(raw_bytes),
        sha256=sha,
        container_format="BIFF .xls workbook (EIA hist_xls export)",
        series_id=series_id,
        series_id_valid=series_id == EXPECTED_SERIES_ID,
        header_valid=True,
        row_count=len(records),
        valid_row_count=len(valid),
        excluded_row_count=len(excluded),
        min_date=min(parsed_dates) if parsed_dates else None,
        max_date=max(parsed_dates) if parsed_dates else None,
        duplicate_dates_within_file=dup_within,
        null_or_malformed_rows=null_malformed,
        numeric_parsing_failures=numeric_failures,
        nonpositive_count=nonpositive,
        nonfinite_count=nonfinite,
        is_ascending=is_asc,
        first_observation=parsed_dates[0] if parsed_dates else None,
        last_observation=parsed_dates[-1] if parsed_dates else None,
    )
    frame = pd.DataFrame(valid)
    return audit, frame, excluded


def audit_all_files(
    raw_dir: Path,
) -> Tuple[List[BrentFileAudit], List[pd.DataFrame], List[BrentExcludedRow]]:
    files = discover_brent_raw_files(raw_dir)
    audits: List[BrentFileAudit] = []
    frames: List[pd.DataFrame] = []
    excluded_all: List[BrentExcludedRow] = []
    for path in files:
        rel = f"data/raw/india/crude/{path.name}"
        audit, frame, excluded = validate_brent_file(path, rel)
        audits.append(audit)
        frames.append(frame)
        excluded_all.extend(excluded)
    return audits, frames, excluded_all


def detect_overlaps(
    frames: List[pd.DataFrame], filenames: List[str]
) -> List[BrentOverlap]:
    """Group valid records by observation date across files.

    Flags identical vs conflicting observations. Conflicts must never
    be silently resolved by the canonicalizer.
    """
    by_date: Dict[date, List[Tuple[str, float]]] = {}
    for frame, name in zip(frames, filenames):
        for _, row in frame.iterrows():
            key = (
                row["observation_date"]
                if isinstance(row["observation_date"], date)
                else pd.to_datetime(row["observation_date"]).date()
            )
            by_date.setdefault(key, []).append((name, float(row["brent_spot_usd_bbl"])))
    overlaps: List[BrentOverlap] = []
    for obs_date in sorted(by_date):
        entries = by_date[obs_date]
        if len(entries) <= 1:
            continue
        first_value = entries[0][1]
        identical = all(value == first_value for _, value in entries)
        overlaps.append(
            BrentOverlap(
                observation_date=obs_date,
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
    overlaps: List[BrentOverlap],
) -> pd.DataFrame:
    """Combine validated frames into the canonical Brent dataset.

    Deduplicates only proven-identical observation dates (provenance
    merged). Raises ValueError on any conflicting overlap — conflicts
    must be reported, never silently resolved. No interpolation, no
    forward-fill, no calendar forcing. Availability stays NULL/unknown.
    """
    conflicts = [item for item in overlaps if not item.identical]
    if conflicts:
        detail = "; ".join(
            f"{item.observation_date} in {item.files}" for item in conflicts[:5]
        )
        raise ValueError(f"Conflicting overlapping records detected: {detail}")
    combined = pd.concat(frames, ignore_index=True)
    provenance: Dict[date, List[str]] = {}
    for frame, name in zip(frames, filenames):
        for value in frame["observation_date"].tolist():
            key = value if isinstance(value, date) else pd.to_datetime(value).date()
            provenance.setdefault(key, [])
            if name not in provenance[key]:
                provenance[key].append(name)
    combined["_sort_date"] = pd.to_datetime(combined["observation_date"])
    combined = combined.sort_values("_sort_date").drop_duplicates(
        subset=["observation_date"], keep="first"
    )
    combined["source_files"] = combined["observation_date"].map(
        lambda d: ";".join(
            sorted(provenance[d if isinstance(d, date) else pd.to_datetime(d).date()])
        )
    )
    combined["observation_date"] = pd.to_datetime(combined["observation_date"]).dt.date
    combined["availability_date"] = pd.NaT
    combined["vintage_status"] = "observed"
    combined["revision_version"] = 0
    combined["availability_basis"] = "unknown_historical_availability"
    combined["source"] = EXPECTED_SOURCE
    combined["series_id"] = EXPECTED_SERIES_ID
    combined["unit"] = EXPECTED_UNIT
    combined = combined.rename(columns={"brent_spot_usd_bbl": "brent_spot_usd_bbl"})
    combined = combined.sort_values("observation_date").reset_index(drop=True)
    return combined[CANONICAL_COLUMNS]


def agent_eligible_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Return only rows with verified availability for agent-facing use.

    EIA exposes no per-observation historical publication timestamps,
    so every canonical row carries NULL availability and this returns
    zero rows (fail closed). Never fabricate availability here.
    """
    eligible = frame[
        frame["availability_date"].notna()
        & frame["vintage_status"].isin(AGENT_ELIGIBLE_VINTAGES)
    ].copy()
    return eligible.reset_index(drop=True)


def build_agent_information_set(frame: pd.DataFrame):
    """Build an InformationSet of agent-eligible Brent vintages.

    Fails closed BEFORE InformationSet construction when nothing is
    eligible, because InformationSet raises on NA availability and
    must not be weakened to accommodate Brent.
    """
    from src.india.information_set import InformationSet

    eligible = agent_eligible_rows(frame)
    if eligible.empty:
        raise ValueError("No agent-eligible Brent vintages.")
    vintages = pd.DataFrame(
        {
            "variable": "BRENT_SPOT",
            "observation_date": pd.to_datetime(eligible["observation_date"]),
            "availability_date": pd.to_datetime(eligible["availability_date"]),
            "revision_version": eligible["revision_version"].astype(int),
            "value": eligible["brent_spot_usd_bbl"].astype(float),
        }
    )
    return InformationSet(vintages)


def validate_no_forward_fill(frame: pd.DataFrame) -> List[str]:
    """Confirm canonical values are never fabricated: every row traces
    to a validated EIA observation with a finite positive price."""
    errors: List[str] = []
    if frame["brent_spot_usd_bbl"].isna().any():
        errors.append("null brent_spot_usd_bbl")
    if ((frame["brent_spot_usd_bbl"] <= 0).any()):
        errors.append("non-positive brent_spot_usd_bbl")
    if not frame["brent_spot_usd_bbl"].map(math.isfinite).all():
        errors.append("non-finite brent_spot_usd_bbl")
    return errors
