"""MCX Gold futures individual-contract canonicalization.

Validates manually acquired MCX Bhav Copy commodity-wise CSVs in place
(raw files are never rewritten) and builds a contract-level canonical
dataset under ``data/processed/india/instruments/``.

MCX observed format (UTF-8, no BOM, descending trade-date order,
unquoted header, quoted rows, dates ``DD Mon YYYY``, expiries
``DDMMMYYYY``):
    Date,Instrument Name,Symbol,Expiry Date,Option Type,Strike Price,
    Open,High,Low,Close,Previous Close,Volume(Lots),Volume(In 000's),
    Value(Lacs),Open Interest(Lots)

All rows observed are Instrument=FUTCOM, Symbol=GOLD, Option Type='-',
Strike Price=0. Each file holds exactly one expiry contract. Two pairs
of files are byte-for-byte duplicates (same contract, two filenames);
they are reconciled through shared provenance, not double-counted.

Canonical schema follows ``IndianGoldFuturesRecord`` (plus provenance):
    trade_date, contract_symbol, expiry_date, open, high, low, close,
    settlement_price, open_interest, volume, turnover, source,
    source_files, ohlc_flag

Field semantics (documented, never silently converted):
- contract_symbol: ``GOLDMMMYYYY`` derived from expiry (adapter
  convention); contract identity is (symbol, expiry_date).
- settlement_price: null — MCX Bhav Copy supplies no separate settlement
  field; Close is NEVER mapped into settlement_price.
- volume: Volume(Lots) as supplied; turnover: Value(Lacs) (INR lacs) as
  supplied; open_interest: Open Interest(Lots). Prices are MCX-quoted
  levels as supplied (conventionally INR per 10g); units never converted.
- ohlc_flag: 'ok' normally; 'expiry_close_outside_range' when
  trade_date == expiry_date and Close falls outside the traded [Low,
  High] (MCX expiry-day closing determination, 49 rows);
  'close_outside_range' for marginal non-expiry cases (5 rows). Flagged
  rows are PRESERVED, never deleted — exact MCX semantics for the
  expiry-day convention are not established from authoritative MCX
  documentation, so the anomaly is classified explicitly instead.

No continuous series is constructed, no roll is applied, no contracts
are back-adjusted. Roll methodology remains a deferred milestone.
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

TRADE_DATE_FORMAT = "%d %b %Y"
EXPIRY_FORMAT = "%d%b%Y"
EXPECTED_INSTRUMENT = "FUTCOM"
EXPECTED_SYMBOL = "GOLD"
CANONICAL_COLUMNS = [
    "trade_date",
    "contract_symbol",
    "expiry_date",
    "open",
    "high",
    "low",
    "close",
    "settlement_price",
    "open_interest",
    "volume",
    "turnover",
    "source",
    "source_files",
    "ohlc_flag",
]


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_gold_raw_files(raw_dir: Path) -> List[Path]:
    """Return sorted MCX gold CSVs. Raw files are never modified."""
    return sorted(raw_dir.glob("*.csv"))


def normalize_header(cells: List[str]) -> List[str]:
    """Strip whitespace from header fields without altering values."""
    return [cell.strip() for cell in cells]


def expected_gold_header() -> List[str]:
    return [
        "Date", "Instrument Name", "Symbol", "Expiry Date", "Option Type",
        "Strike Price", "Open", "High", "Low", "Close", "Previous Close",
        "Volume(Lots)", "Volume(In 000's)", "Value(Lacs)", "Open Interest(Lots)",
    ]


def header_matches_gold_schema(normalized: List[str]) -> bool:
    """Match the actual observed MCX Bhav Copy header exactly."""
    return normalized == expected_gold_header()


def parse_trade_date(value: str) -> date:
    """Parse 'DD Mon YYYY' trade dates. Raises on malformed."""
    text = value.strip()
    if not text:
        raise ValueError("empty date")
    return datetime.strptime(text, TRADE_DATE_FORMAT).date()


def parse_expiry(value: str) -> date:
    """Parse 'DDMMMYYYY' expiries (e.g. 05FEB2004). Raises on malformed."""
    text = value.strip().upper()
    if not text:
        raise ValueError("empty expiry")
    return datetime.strptime(text, EXPIRY_FORMAT).date()


def contract_symbol_for(expiry: date) -> str:
    """Adapter-convention symbol GOLDMMMYYYY (e.g. GOLDFEB2004)."""
    return f"GOLD{expiry.strftime('%b%Y')}".upper()


def classify_ohlc(
    trade: date, expiry: date, o_val: Optional[float], h_val: Optional[float],
    l_val: Optional[float], c_val: float, volume: float,
) -> str:
    """Classify OHLC consistency without deleting. Returns flag string."""
    if o_val is None or h_val is None or l_val is None:
        # MCX publishes no traded OHLC on zero-volume sessions while still
        # publishing Close/Previous Close/OI. Preserved with null OHLC.
        return "no_trade_ohlc_null"
    consistent = (
        h_val >= o_val
        and h_val >= c_val
        and h_val >= l_val
        and l_val <= o_val
        and l_val <= c_val
        and h_val >= l_val
    )
    if consistent:
        return "ok"
    if trade == expiry:
        return "expiry_close_outside_range"
    return "close_outside_range"


@dataclass
class GoldExcludedRow:
    source_file: str
    date_text: str
    reason: str


@dataclass
class GoldFileAudit:
    filename: str
    rel_path: str
    byte_size: int
    sha256: str
    header: List[str]
    header_valid: bool
    has_bom: bool
    instruments_observed: List[str]
    symbols_observed: List[str]
    expiries_observed: List[str]
    row_count: int
    parsed_row_count: int
    valid_row_count: int
    excluded_row_count: int
    min_trade_date: Optional[date]
    max_trade_date: Optional[date]
    duplicate_keys_within_file: int
    null_or_malformed_rows: int
    numeric_parsing_failures: int
    nonpositive_count: int
    expiry_before_trade_count: int
    ohlc_flagged_count: int
    is_descending: bool
    is_ascending: bool


@dataclass
class GoldOverlap:
    trade_date: date
    expiry: str
    files: List[str]
    identical: bool
    records: List[Dict[str, Any]] = field(default_factory=list)


def validate_gold_file(
    path: Path, rel_path: str
) -> Tuple[GoldFileAudit, pd.DataFrame, List[GoldExcludedRow]]:
    """Validate one MCX file in place.

    Returns (audit, valid-records frame, excluded rows with reasons).
    """
    raw_bytes = path.read_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()
    has_bom = raw_bytes[:3] == b"\xef\xbb\xbf"
    parsed = list(csv.reader(io.StringIO(raw_bytes.decode("utf-8-sig"))))
    if not parsed:
        raise ValueError(f"{path.name}: empty file")
    header = normalize_header(parsed[0])
    header_valid = header_matches_gold_schema(header)

    records: List[Dict[str, Any]] = []
    excluded: List[GoldExcludedRow] = []
    instruments: List[str] = []
    symbols: List[str] = []
    expiries: List[str] = []
    null_malformed = 0
    numeric_failures = 0
    nonpositive = 0
    expiry_before_trade = 0
    flagged = 0
    trade_dates: List[date] = []
    seen: Dict[Tuple[date, str], int] = {}

    for row in parsed[1:]:
        if len(row) != 15:
            null_malformed += 1
            continue
        fields = [v.strip() for v in row]
        # Date/Symbol/Expiry/Close/Volume/Value/OI must always be present;
        # empty Open/High/Low on zero-volume sessions is an MCX no-trade
        # convention (Close still published), not malformation.
        if any(fields[i] == "" for i in (0, 1, 2, 3, 9, 11, 13, 14)):
            null_malformed += 1
            continue
        inst, sym, exp_text = fields[1], fields[2], fields[3]
        if inst not in instruments:
            instruments.append(inst)
        if sym not in symbols:
            symbols.append(sym)
        if exp_text not in expiries:
            expiries.append(exp_text)
        try:
            trade = parse_trade_date(fields[0])
            expiry = parse_expiry(exp_text)
        except ValueError:
            null_malformed += 1
            continue
        try:
            c_val = float(fields[9])
            vol_val = float(fields[11])
            val_val = float(fields[13])
            oi_val = float(fields[14])
        except ValueError:
            numeric_failures += 1
            continue
        ohlc_missing = fields[6] == "" or fields[7] == "" or fields[8] == ""
        if ohlc_missing and vol_val != 0:
            # Traded volume without traded OHLC is a source data error.
            numeric_failures += 1
            excluded.append(
                GoldExcludedRow(
                    source_file=path.name,
                    date_text=fields[0],
                    reason="missing OHLC despite nonzero volume",
                )
            )
            continue
        try:
            o_val = None if fields[6] == "" else float(fields[6])
            h_val = None if fields[7] == "" else float(fields[7])
            l_val = None if fields[8] == "" else float(fields[8])
        except ValueError:
            numeric_failures += 1
            continue
        if inst != EXPECTED_INSTRUMENT or sym != EXPECTED_SYMBOL:
            excluded.append(
                GoldExcludedRow(
                    source_file=path.name,
                    date_text=fields[0],
                    reason=f"unexpected instrument/symbol: {inst}/{sym}",
                )
            )
            continue
        if expiry < trade:
            expiry_before_trade += 1
            excluded.append(
                GoldExcludedRow(
                    source_file=path.name,
                    date_text=fields[0],
                    reason=f"expiry {exp_text} before trade date",
                )
            )
            continue
        if o_val is not None and (o_val <= 0 or h_val <= 0 or l_val <= 0):
            nonpositive += 1
            excluded.append(
                GoldExcludedRow(
                    source_file=path.name,
                    date_text=fields[0],
                    reason="non-positive OHLC price",
                )
            )
            continue
        if c_val <= 0:
            nonpositive += 1
            excluded.append(
                GoldExcludedRow(
                    source_file=path.name,
                    date_text=fields[0],
                    reason="non-positive Close price",
                )
            )
            continue
        if vol_val < 0 or oi_val < 0 or val_val < 0:
            nonpositive += 1
            excluded.append(
                GoldExcludedRow(
                    source_file=path.name,
                    date_text=fields[0],
                    reason="negative volume/OI/value",
                )
            )
            continue
        trade_dates.append(trade)
        key = (trade, exp_text)
        seen[key] = seen.get(key, 0) + 1
        flag = classify_ohlc(trade, expiry, o_val, h_val, l_val, c_val, vol_val)
        if flag != "ok":
            flagged += 1
        records.append(
            {
                "trade_date": trade,
                "contract_symbol": contract_symbol_for(expiry),
                "expiry_date": expiry,
                "expiry_text": exp_text,
                "open": o_val,
                "high": h_val,
                "low": l_val,
                "close": c_val,
                "settlement_price": None,
                "open_interest": oi_val,
                "volume": vol_val,
                "turnover": val_val,
                "source_file": path.name,
                "ohlc_flag": flag,
            }
        )

    dup_within = sum(count - 1 for count in seen.values() if count > 1)
    is_desc = (
        all(trade_dates[i] >= trade_dates[i + 1] for i in range(len(trade_dates) - 1))
        if len(trade_dates) > 1
        else True
    )
    is_asc = (
        all(trade_dates[i] <= trade_dates[i + 1] for i in range(len(trade_dates) - 1))
        if len(trade_dates) > 1
        else True
    )
    audit = GoldFileAudit(
        filename=path.name,
        rel_path=rel_path,
        byte_size=len(raw_bytes),
        sha256=sha,
        header=header,
        header_valid=header_valid,
        has_bom=has_bom,
        instruments_observed=instruments,
        symbols_observed=symbols,
        expiries_observed=expiries,
        row_count=len(parsed) - 1,
        parsed_row_count=len(trade_dates),
        valid_row_count=len(records),
        excluded_row_count=len(excluded),
        min_trade_date=min(trade_dates) if trade_dates else None,
        max_trade_date=max(trade_dates) if trade_dates else None,
        duplicate_keys_within_file=dup_within,
        null_or_malformed_rows=null_malformed,
        numeric_parsing_failures=numeric_failures,
        nonpositive_count=nonpositive,
        expiry_before_trade_count=expiry_before_trade,
        ohlc_flagged_count=flagged,
        is_descending=is_desc,
        is_ascending=is_asc,
    )
    frame = pd.DataFrame(records)
    return audit, frame, excluded


def audit_all_files(
    raw_dir: Path,
) -> Tuple[List[GoldFileAudit], List[pd.DataFrame], List[GoldExcludedRow]]:
    files = discover_gold_raw_files(raw_dir)
    audits: List[GoldFileAudit] = []
    frames: List[pd.DataFrame] = []
    excluded_all: List[GoldExcludedRow] = []
    for path in files:
        rel = f"data/raw/india/gold/{path.name}"
        audit, frame, excluded = validate_gold_file(path, rel)
        audits.append(audit)
        frames.append(frame)
        excluded_all.extend(excluded)
    return audits, frames, excluded_all


def _num(value: Any) -> Optional[float]:
    """NaN-safe numeric normalization so identical rows compare identical."""
    if value is None:
        return None
    number = float(value)
    return None if number != number else number  # NaN -> None


def detect_overlaps(
    frames: List[pd.DataFrame], filenames: List[str]
) -> List[GoldOverlap]:
    """Group valid records by (trade_date, expiry) natural key.

    Flags identical vs conflicting observations across files.
    """
    by_key: Dict[Tuple[date, str], List[Tuple[str, Tuple[float, ...]]]] = {}
    for frame, name in zip(frames, filenames):
        for _, row in frame.iterrows():
            trade = (
                row["trade_date"]
                if isinstance(row["trade_date"], date)
                else pd.to_datetime(row["trade_date"]).date()
            )
            key = (trade, str(row["expiry_text"]))
            values = (
                _num(row["open"]),
                _num(row["high"]),
                _num(row["low"]),
                float(row["close"]),
                float(row["open_interest"]),
                float(row["volume"]),
                float(row["turnover"]),
            )
            by_key.setdefault(key, []).append((name, values))
    overlaps: List[GoldOverlap] = []
    for (trade, expiry) in sorted(by_key):
        entries = by_key[(trade, expiry)]
        if len(entries) <= 1:
            continue
        first_values = entries[0][1]
        identical = all(values == first_values for _, values in entries)
        overlaps.append(
            GoldOverlap(
                trade_date=trade,
                expiry=expiry,
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
    overlaps: List[GoldOverlap],
) -> pd.DataFrame:
    """Combine validated frames, dedup only proven identical natural keys.

    Raises ValueError if any conflicting overlap exists — the caller must
    report the conflict rather than choosing a record arbitrarily. No
    continuous series is constructed and no roll is applied.
    """
    conflicts = [item for item in overlaps if not item.identical]
    if conflicts:
        detail = "; ".join(
            f"{item.trade_date}/{item.expiry} in {item.files}" for item in conflicts[:5]
        )
        raise ValueError(f"Conflicting overlapping records detected: {detail}")
    combined = pd.concat(frames, ignore_index=True)
    # Provenance: every raw file that carried this natural key.
    provenance: Dict[Tuple[date, str], List[str]] = {}
    for frame, name in zip(frames, filenames):
        for _, row in frame.iterrows():
            trade = (
                row["trade_date"]
                if isinstance(row["trade_date"], date)
                else pd.to_datetime(row["trade_date"]).date()
            )
            key = (trade, str(row["expiry_text"]))
            provenance.setdefault(key, [])
            if name not in provenance[key]:
                provenance[key].append(name)
    combined["_sort_date"] = pd.to_datetime(combined["trade_date"])
    combined = combined.sort_values(["_sort_date", "expiry_date"]).drop_duplicates(
        subset=["trade_date", "expiry_text"], keep="first"
    )
    combined["source_files"] = combined.apply(
        lambda r: ";".join(
            sorted(
                provenance[
                    (
                        r["trade_date"]
                        if isinstance(r["trade_date"], date)
                        else pd.to_datetime(r["trade_date"]).date(),
                        str(r["expiry_text"]),
                    )
                ]
            )
        ),
        axis=1,
    )
    combined["trade_date"] = pd.to_datetime(combined["trade_date"]).dt.date
    combined["expiry_date"] = pd.to_datetime(combined["expiry_date"]).dt.date
    combined["source"] = "MCX"
    combined = combined.sort_values(["trade_date", "contract_symbol"]).reset_index(drop=True)
    return combined[CANONICAL_COLUMNS]
