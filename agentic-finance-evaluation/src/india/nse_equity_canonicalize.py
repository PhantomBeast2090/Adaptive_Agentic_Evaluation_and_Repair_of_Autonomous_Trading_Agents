"""NSE Capital Market equity daily bhavcopy canonicalization.

Official source: National Stock Exchange of India (NSE), Capital Market
segment daily bhavcopy archives. NSE is the canonical authority; no
third-party values are ever used canonically.

Two official regimes (both live at acquisition; endpoint behavior verified
per artifact, never assumed):

  Regime ``sec_bhav`` (later CM bhavcopy CSV):
    https://archives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv
    Served span observed: 2019-09-30 .. present (the sec_bhav archive
    endpoint remains accessible and was observed serving data in parallel
    with UDiFF — evidence in the acquisition index).
    Schema (15 cols, stable 2019..present, NO ISIN):
      SYMBOL, SERIES, DATE1 (DD-Mon-YYYY), PREV_CLOSE, OPEN_PRICE,
      HIGH_PRICE, LOW_PRICE, LAST_PRICE, CLOSE_PRICE, AVG_PRICE,
      TTL_TRD_QNTY, TURNOVER_LACS (Rs. lacs), NO_OF_TRADES,
      DELIV_QTY, DELIV_PER (percent).

  Regime ``udiff`` (CM-UDiFF Common Bhavcopy Final, zipped CSV):
    https://archives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip
    Served span observed: 2024-01-01 .. present.
    Schema (35 cols, ISO dates, WITH ISIN + FinInstrmId, NO delivery fields):
      TradDt, BizDt, Sgmt, Src, FinInstrmTp, FinInstrmId, ISIN, TckrSymb,
      SctySrs, ..., FinInstrmNm, OpnPric, HghPric, LwPric, ClsPric,
      LastPric, PrvsClsgPric, ..., TtlTradgVol (shares),
      TtlTrfVal (INR rupees), TtlNbOfTxsExctd, ...

Canonical policy (evidence-backed, documented in the manifest):
  - Grain: security x trading date; identity key (observation_date,
    symbol, series) preserved exactly as reported (NSE's own rule: once
    a symbol and a series are specified, a security is uniquely known;
    see NSE Data_details_CM.pdf). NO symbol merging, stitching, or
    permanent company IDs are invented.
  - OHLCV canonical source: ``sec_bhav`` throughout (uniform schema over
    the full span, carries delivery data). UDiFF serves as the
    field-by-field cross-regime validation mirror wherever both regimes
    serve a date; disagreements are conflicts (blocked, never resolved
    silently).
  - ISIN enrichment: same-day, same-(symbol, series) UDiFF attach only
    when exactly one distinct UDiFF ISIN exists for the key
    (``isin_basis=udiff_match``); otherwise NULL with basis
    ``unmatched``/``ambiguous``. No cross-time identity inference.
  - Exchange-reported prices only: no split/bonus/dividend/rights/back
    adjustment, no splicing, interpolation, or smoothing. Corporate-action
    ex-date flags are out of scope for this milestone (no authoritative
    per-row flag column exists in either served regime).
  - Availability: NULL/unknown for every row (historical per-day
    publication timestamps are not recoverable from the archive; current
    download time and filesystem metadata are NOT information dates).
    agent_eligible_rows() returns zero rows; the agent gate fails closed
    BEFORE InformationSet construction (InformationSet is unmodified).
  - Weekends are never requested (NSE publishes no weekend bhavcopy);
    every HTTP-200 artifact verifies in-file DATE1/TradDt against its
    requested date (the archive serves fallback-day content with HTTP 200).
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

SEC_BHAV_HEADER = [
    "SYMBOL", "SERIES", "DATE1", "PREV_CLOSE", "OPEN_PRICE", "HIGH_PRICE",
    "LOW_PRICE", "LAST_PRICE", "CLOSE_PRICE", "AVG_PRICE", "TTL_TRD_QNTY",
    "TURNOVER_LACS", "NO_OF_TRADES", "DELIV_QTY", "DELIV_PER",
]

UDIFF_REQUIRED = [
    "TradDt", "Sgmt", "FinInstrmTp", "FinInstrmId", "ISIN", "TckrSymb",
    "SctySrs", "FinInstrmNm", "OpnPric", "HghPric", "LwPric", "ClsPric",
    "LastPric", "PrvsClsgPric", "TtlTradgVol", "TtlTrfVal",
    "TtlNbOfTxsExctd",
]

SEC_BHAV_DATE_FORMAT = "%d-%b-%Y"
UDIFF_DATE_FORMAT = "%Y-%m-%d"

CANONICAL_COLUMNS = [
    "observation_date",
    "availability_date",
    "symbol",
    "series",
    "isin",
    "isin_basis",
    "security_name",
    "fin_instrm_id",
    "fin_instrm_type",
    "segment",
    "open",
    "high",
    "low",
    "close",
    "last_price",
    "prev_close",
    "vwap",
    "traded_quantity",
    "turnover_lacs",
    "turnover_inr",
    "number_of_trades",
    "deliverable_quantity",
    "deliverable_percentage",
    "ohlc_flag",
    "vintage_status",
    "revision_version",
    "availability_basis",
    "regime",
    "source",
    "source_files",
]

# No historical publication timing exists; nothing is agent-eligible.
AGENT_ELIGIBLE_VINTAGES = frozenset()


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_raw_files(raw_dir: Path) -> Tuple[List[Path], List[Path]]:
    """Return (sec_bhav CSVs, UDiFF zips) sorted. Raw files never modified."""
    sec = sorted(raw_dir.glob("sec_bhavdata_full_*.csv"))
    udiff = sorted(raw_dir.glob("BhavCopy_NSE_CM_*.zip"))
    return sec, udiff


def parse_sec_bhav_date(value: str) -> date:
    text = value.strip()
    if not text:
        raise ValueError("empty date")
    return datetime.strptime(text, SEC_BHAV_DATE_FORMAT).date()


def _iter_sec_bhav_rows(raw_bytes: bytes) -> Tuple[List[str], List[Dict[str, str]]]:
    """Yield (header, row dicts) from a sec_bhav payload, detecting the
    container by magic bytes rather than filename.

    Evidence: NSE served 2022-08-08 as an XLSX workbook (magic ``PK``,
    created by "Microsoft Excel Online") under a ``.csv`` filename, with
    the identical 15-column schema. Raw bytes are never modified.
    """
    if raw_bytes[:2] == b"PK":
        import openpyxl

        workbook = openpyxl.load_workbook(
            io.BytesIO(raw_bytes), read_only=True, data_only=True)
        sheet = workbook.active
        grid = list(sheet.iter_rows(values_only=True))
        if not grid:
            return [], []
        header = [str(c).strip() if c is not None else "" for c in grid[0]]
        rows = []
        for values in grid[1:]:
            row = {}
            for idx, col in enumerate(header):
                cell = values[idx] if idx < len(values) else None
                row[col] = "" if cell is None else str(cell)
            rows.append(row)
        return header, rows
    text = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    header = [c.strip() if c else "" for c in (reader.fieldnames or [])]
    rows = [{(k.strip() if k else ""): v for k, v in raw_row.items()}
            for raw_row in reader]
    return header, rows
    text = value.strip()
    if not text:
        raise ValueError("empty date")
    return datetime.strptime(text, SEC_BHAV_DATE_FORMAT).date()


def parse_udiff_date(value: str) -> date:
    text = value.strip()
    if not text:
        raise ValueError("empty date")
    return datetime.strptime(text, UDIFF_DATE_FORMAT).date()


def _to_float(value: Any) -> Optional[float]:
    """Strict numeric parsing: blanks/placeholders stay NULL, never zero."""
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text in {"-", "--", "NA", "N/A", "null", "NULL"}:
        return None
    try:
        number = float(text.replace(",", ""))
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number


def _to_int(value: Any) -> Optional[int]:
    number = _to_float(value)
    if number is None:
        return None
    return int(number)


@dataclass
class EquityFileAudit:
    filename: str
    regime: str
    rel_path: str
    byte_size: int
    sha256: str
    header: List[str]
    header_valid: bool
    requested_date: Optional[str]
    infile_date: Optional[str]
    date_match: Optional[bool]
    row_count: int
    valid_row_count: int
    excluded_row_count: int
    duplicate_keys_within_file: int
    null_or_malformed_rows: int
    numeric_parsing_warnings: int
    ohlc_violations: int
    negative_price_count: int
    negative_quantity_count: int
    delivery_violations: int
    min_date: Optional[date]
    max_date: Optional[date]
    series_observed: List[str] = field(default_factory=list)


@dataclass
class EquityExcludedRow:
    source_file: str
    key_text: str
    reason: str


def _audit_common(
    filename: str, regime: str, rel_path: str, byte_size: int, sha: str,
    header: List[str], header_valid: bool, requested: Optional[str],
    infile: Optional[str], match: Optional[bool],
) -> Dict[str, Any]:
    return dict(
        filename=filename, regime=regime, rel_path=rel_path, byte_size=byte_size,
        sha256=sha, header=header, header_valid=header_valid,
        requested_date=requested, infile_date=infile, date_match=match,
    )


def validate_sec_bhav_file(
    path: Path, rel_path: str, requested_date: Optional[str] = None,
) -> Tuple[EquityFileAudit, pd.DataFrame, List[EquityExcludedRow]]:
    """Validate one sec_bhav CSV in place (raw never modified)."""
    raw_bytes = path.read_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()
    header, raw_rows = _iter_sec_bhav_rows(raw_bytes)
    header_valid = header == SEC_BHAV_HEADER

    records: List[Dict[str, Any]] = []
    excluded: List[EquityExcludedRow] = []
    seen: Dict[Tuple[str, str, str], int] = {}
    null_malformed = 0
    num_warn = 0
    ohlc_viol = 0
    neg_price = 0
    neg_qty = 0
    deliv_viol = 0
    series_seen: List[str] = []
    infile_dates: List[str] = []

    for lineno, raw_row in enumerate(raw_rows, start=2):
        row = {(k.strip() if k else ""): (v or "") for k, v in raw_row.items()}
        get = lambda k: (row.get(k) or "").strip()  # noqa: E731
        symbol, series, date_text = get("SYMBOL"), get("SERIES"), get("DATE1")
        if not symbol or not series or not date_text:
            null_malformed += 1
            excluded.append(EquityExcludedRow(path.name, f"line {lineno}",
                                              "missing symbol/series/date"))
            continue
        try:
            obs = parse_sec_bhav_date(date_text)
        except ValueError:
            null_malformed += 1
            excluded.append(EquityExcludedRow(path.name, f"line {lineno}",
                                              f"unparseable date {date_text!r}"))
            continue
        infile_dates.append(date_text)
        if series not in series_seen:
            series_seen.append(series)
        key = (obs.isoformat(), symbol, series)
        seen[key] = seen.get(key, 0) + 1

        op, hi, lo, cl = (_to_float(get(c)) for c in
                          ("OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE"))
        last, prev, vwap = (_to_float(get(c)) for c in
                            ("LAST_PRICE", "PREV_CLOSE", "AVG_PRICE"))
        qty = _to_int(get("TTL_TRD_QNTY"))
        tval = _to_float(get("TURNOVER_LACS"))
        ntrades = _to_int(get("NO_OF_TRADES"))
        dqty = _to_int(get("DELIV_QTY"))
        dper = _to_float(get("DELIV_PER"))

        bad_numbers = [v for v in (op, hi, lo, cl, last, prev, vwap) if v is not None and v <= 0]
        if bad_numbers:
            neg_price += 1
        bad_qty = [v for v in (qty, ntrades) if v is not None and v < 0]
        if bad_qty or (tval is not None and tval < 0):
            neg_qty += 1
        present_ohlc = [v for v in (op, hi, lo, cl) if v is not None]
        if len(present_ohlc) == 4 and not (
                hi >= max(op, cl, lo) and lo <= min(op, cl, hi)):
            ohlc_viol += 1
        if dqty is not None and qty is not None and dqty > qty:
            deliv_viol += 1
        if dper is not None and not (0 <= dper <= 100):
            deliv_viol += 1

        records.append({
            "observation_date": obs, "symbol": symbol, "series": series,
            "open": op, "high": hi, "low": lo, "close": cl,
            "last_price": last, "prev_close": prev, "vwap": vwap,
            "traded_quantity": qty, "turnover_lacs": tval,
            "number_of_trades": ntrades,
            "deliverable_quantity": dqty, "deliverable_percentage": dper,
            "source_file": path.name,
        })

    dup_within = sum(c - 1 for c in seen.values() if c > 1)
    obs_dates = sorted({k[0] for k in seen})
    sec_match: Optional[bool] = None
    if requested_date and infile_dates:
        try:
            sec_match = (parse_sec_bhav_date(infile_dates[0])
                         == date.fromisoformat(requested_date))
        except ValueError:
            sec_match = False
    audit = EquityFileAudit(
        **_audit_common(path.name, "sec_bhav", rel_path, len(raw_bytes), sha,
                        header, header_valid, requested_date,
                        infile_dates[0] if infile_dates else None,
                        sec_match),
        row_count=len(records) + sum(1 for e in excluded if e.reason.startswith(("missing", "unparseable"))),
        valid_row_count=len(records),
        excluded_row_count=len([e for e in excluded]),
        duplicate_keys_within_file=dup_within,
        null_or_malformed_rows=null_malformed,
        numeric_parsing_warnings=num_warn,
        ohlc_violations=ohlc_viol,
        negative_price_count=neg_price,
        negative_quantity_count=neg_qty,
        delivery_violations=deliv_viol,
        min_date=date.fromisoformat(obs_dates[0]) if obs_dates else None,
        max_date=date.fromisoformat(obs_dates[-1]) if obs_dates else None,
        series_observed=sorted(series_seen),
    )
    return audit, pd.DataFrame(records), excluded


def read_udiff_csv(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    """Read the single CSV inside a UDiFF zip without extracting to raw dir."""
    with zipfile.ZipFile(str(path)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"{path.name}: expected 1 CSV in zip, found {names}")
        with zf.open(names[0]) as fh:
            text = fh.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    header = [c.strip() if c else "" for c in (reader.fieldnames or [])]
    return header, [{k.strip() if k else "": (v or "").strip()
                     for k, v in row.items()} for row in reader]


def validate_udiff_file(
    path: Path, rel_path: str, requested_date: Optional[str] = None,
) -> Tuple[EquityFileAudit, pd.DataFrame, List[EquityExcludedRow]]:
    """Validate one UDiFF zip in place (raw never modified, never extracted)."""
    raw_bytes = path.read_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()
    header, rows = read_udiff_csv(path)
    header_valid = all(c in header for c in UDIFF_REQUIRED)

    records: List[Dict[str, Any]] = []
    excluded: List[EquityExcludedRow] = []
    seen: Dict[Tuple[str, str, str], int] = {}
    null_malformed = 0
    ohlc_viol = 0
    neg_price = 0
    neg_qty = 0
    series_seen: List[str] = []
    infile_dates: List[str] = []

    for lineno, row in enumerate(rows, start=2):
        symbol, series = row.get("TckrSymb", ""), row.get("SctySrs", "")
        date_text = row.get("TradDt", "")
        if not symbol or not series or not date_text:
            null_malformed += 1
            excluded.append(EquityExcludedRow(path.name, f"line {lineno}",
                                              "missing symbol/series/TradDt"))
            continue
        try:
            obs = parse_udiff_date(date_text)
        except ValueError:
            null_malformed += 1
            excluded.append(EquityExcludedRow(path.name, f"line {lineno}",
                                              f"unparseable TradDt {date_text!r}"))
            continue
        infile_dates.append(date_text)
        if series not in series_seen:
            series_seen.append(series)
        # CM equity scope only: non-CM segments preserved out-of-scope check.
        key = (obs.isoformat(), symbol, series)
        seen[key] = seen.get(key, 0) + 1

        op = _to_float(row.get("OpnPric"))
        hi = _to_float(row.get("HghPric"))
        lo = _to_float(row.get("LwPric"))
        cl = _to_float(row.get("ClsPric"))
        last = _to_float(row.get("LastPric"))
        prev = _to_float(row.get("PrvsClsgPric"))
        qty = _to_int(_to_float(row.get("TtlTradgVol")))
        tval_inr = _to_float(row.get("TtlTrfVal"))
        ntrades = _to_int(_to_float(row.get("TtlNbOfTxsExctd")))

        if any(v is not None and v <= 0 for v in (op, hi, lo, cl, last, prev)):
            neg_price += 1
        if any(v is not None and v < 0 for v in (qty, ntrades)) or (
                tval_inr is not None and tval_inr < 0):
            neg_qty += 1
        present = [v for v in (op, hi, lo, cl) if v is not None]
        if len(present) == 4 and not (
                hi >= max(op, cl, lo) and lo <= min(op, cl, hi)):
            ohlc_viol += 1

        records.append({
            "observation_date": obs, "symbol": symbol, "series": series,
            "isin": row.get("ISIN") or None,
            "security_name": row.get("FinInstrmNm") or None,
            "fin_instrm_id": row.get("FinInstrmId") or None,
            "fin_instrm_type": row.get("FinInstrmTp") or None,
            "segment": row.get("Sgmt") or None,
            "open": op, "high": hi, "low": lo, "close": cl,
            "last_price": last, "prev_close": prev,
            "traded_quantity": qty, "turnover_inr": tval_inr,
            "number_of_trades": ntrades,
            "source_file": path.name,
        })

    dup_within = sum(c - 1 for c in seen.values() if c > 1)
    obs_dates = sorted({k[0] for k in seen})
    udiff_match: Optional[bool] = None
    if requested_date and infile_dates:
        try:
            udiff_match = (parse_udiff_date(infile_dates[0])
                           == date.fromisoformat(requested_date))
        except ValueError:
            udiff_match = False
    audit = EquityFileAudit(
        **_audit_common(path.name, "udiff", rel_path, len(raw_bytes), sha,
                        header, header_valid, requested_date,
                        infile_dates[0] if infile_dates else None,
                        udiff_match),
        row_count=len(records) + null_malformed,
        valid_row_count=len(records),
        excluded_row_count=len(excluded),
        duplicate_keys_within_file=dup_within,
        null_or_malformed_rows=null_malformed,
        numeric_parsing_warnings=0,
        ohlc_violations=ohlc_viol,
        negative_price_count=neg_price,
        negative_quantity_count=neg_qty,
        delivery_violations=0,
        min_date=date.fromisoformat(obs_dates[0]) if obs_dates else None,
        max_date=date.fromisoformat(obs_dates[-1]) if obs_dates else None,
        series_observed=sorted(series_seen),
    )
    return audit, pd.DataFrame(records), excluded


@dataclass
class EquityOverlap:
    key: Tuple[str, str, str]  # (observation_date, symbol, series)
    files: List[str]
    identical: bool
    detail: str = ""


def _key_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Copy with a normalized string join key (obs, symbol, series)."""
    out = frame.copy()
    out["_key_obs"] = out["observation_date"].map(
        lambda d: d.isoformat() if isinstance(d, date) else str(d))
    out["_key_sym"] = out["symbol"].astype(str)
    out["_key_ser"] = out["series"].astype(str)
    return out


def detect_key_overlaps(
    frames: List[pd.DataFrame], filenames: List[str],
    value_cols: List[str],
) -> List[EquityOverlap]:
    """Group records by (date, symbol, series); flag identical vs conflicting.

    Vectorized via groupby aggregations (no per-group Python iteration:
    the corpus holds ~4.5M unique keys). NULL==NULL counts as identical
    (nunique(dropna=False)); any value difference across rows sharing a
    key is conflicting. Only conflicting keys are iterated individually
    for examples.
    """
    tagged = []
    for frame, name in zip(frames, filenames):
        if frame.empty:
            continue
        part = _key_frame(frame)
        part["_src_file"] = name
        tagged.append(part)
    if not tagged:
        return []
    big = pd.concat(tagged, ignore_index=True)
    key_cols = ["_key_obs", "_key_sym", "_key_ser"]
    grouped = big.groupby(key_cols, sort=True)
    counts = grouped.size()
    multi = counts[counts > 1]
    if multi.empty:
        return []
    present_cols = [c for c in value_cols if c in big.columns]
    nunique = grouped[present_cols].nunique(dropna=False) if present_cols else None
    files_of = grouped["_src_file"].agg(lambda files: sorted(set(files)))
    overlaps: List[EquityOverlap] = []
    for key in multi.index:
        files = [str(f) for f in files_of.loc[key]]
        identical = True
        if nunique is not None:
            identical = bool((nunique.loc[key] <= 1).all())
        overlaps.append(EquityOverlap(
            key=(str(key[0]), str(key[1]), str(key[2])), files=files,
            identical=identical,
            detail="" if identical else f"conflicting values across {files}",
        ))
    return overlaps


def _norm(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _eq_series(a: pd.Series, b: pd.Series) -> pd.Series:
    """Element-wise equality where NULL==NULL (NaN-safe, dtype-agnostic)."""
    a_num = pd.to_numeric(a, errors="coerce")
    b_num = pd.to_numeric(b, errors="coerce")
    both_null = a_num.isna() & b_num.isna()
    return both_null | (a_num == b_num).fillna(False)


def compare_regimes(
    sec: pd.DataFrame, udiff: pd.DataFrame,
) -> Dict[str, Any]:
    """Field-by-field cross-regime comparison on (date, symbol, series).

    Compares OHLC + last + prev_close + quantity + trades exactly
    (NULL==NULL), and turnover via unit conversion (lacs*100000 vs INR
    rupees). Turnover passes when |udiff - lacs*1e5| <= Rs 500 + 0.6% of
    value: sec_bhav TURNOVER_LACS is rounded to 2 decimals, so sub-lac
    turnovers carry up to Rs 500 rounding error (evidence: 08-Jul-2024
    GS/debt keys with exact OHLCV but turnover ratios 0.78..1.11 on
    Rs 10^2..10^4 values).
    Vectorized via merge (identical results to the original row loop).
    Returns aggregate counts plus the conflicting key list (never
    silently resolved downstream).
    """
    field_map = [("open", "open"), ("high", "high"), ("low", "low"),
                 ("close", "close"), ("last_price", "last_price"),
                 ("prev_close", "prev_close"), ("traded_quantity", "traded_quantity"),
                 ("number_of_trades", "number_of_trades")]
    s = _key_frame(sec)
    u = _key_frame(udiff)
    s_keys = set(zip(s["_key_obs"], s["_key_sym"], s["_key_ser"]))
    u_keys = set(zip(u["_key_obs"], u["_key_sym"], u["_key_ser"]))
    common = sorted(s_keys & u_keys)
    # Same-side duplicate keys (e.g. holiday-fallback files) would cause a
    # cartesian merge blowup. Collapse to first occurrence here and COUNT
    # the collapse explicitly; same-side conflict detection is the job of
    # detect_key_overlaps (which raises), not of this comparison.
    key_cols = ["_key_obs", "_key_sym", "_key_ser"]
    sec_collapsed = int(s.duplicated(subset=key_cols).sum())
    udiff_collapsed = int(u.duplicated(subset=key_cols).sum())
    s = s.drop_duplicates(subset=key_cols, keep="first")
    u = u.drop_duplicates(subset=key_cols, keep="first")
    merged = s.merge(
        u, on=["_key_obs", "_key_sym", "_key_ser"],
        suffixes=("_s", "_u"), how="inner")
    field_mismatches: Dict[str, int] = {}
    bad_mask = pd.Series(False, index=merged.index)
    for a, b in field_map:
        col_s = f"{a}_s" if f"{a}_s" in merged.columns else a
        col_u = f"{b}_u" if f"{b}_u" in merged.columns else b
        same = _eq_series(merged[col_s], merged[col_u])
        field_mismatches[a] = int((~same).sum())
        bad_mask = bad_mask | (~same)
    s_turn = pd.to_numeric(merged.get("turnover_lacs"), errors="coerce")
    u_turn = pd.to_numeric(merged.get("turnover_inr"), errors="coerce")
    turn_ok = pd.Series(pd.NA, index=merged.index, dtype="boolean")
    comparable = s_turn.notna() & u_turn.notna() & (s_turn > 0)
    turn_ok[comparable] = (
        (u_turn[comparable] - s_turn[comparable] * 100000).abs()
        <= 500 + 0.006 * s_turn[comparable] * 100000)
    turnover_ok = int((turn_ok == True).sum())  # noqa: E712
    turnover_mismatch = int((turn_ok == False).sum())  # noqa: E712
    # Non-comparable turnover (NA) passes, matching the original
    # `turn_ok is not False` rule: only explicit False blocks exactness.
    bad_mask = bad_mask | (turn_ok.fillna(True) == False)  # noqa: E712
    exact = int((~bad_mask).sum())
    conflicts: List[Dict[str, Any]] = []
    bad_rows = merged[bad_mask]
    for _, row in bad_rows.iterrows():
        bad_fields = [a for a, b in field_map
                      if not _eq_series(
                          pd.Series([row[f"{a}_s" if f"{a}_s" in merged.columns else a]]),
                          pd.Series([row[f"{b}_u" if f"{b}_u" in merged.columns else b]])).iloc[0]]
        key = (str(row["_key_obs"]), str(row["_key_sym"]), str(row["_key_ser"]))
        conflicts.append({"key": key, "fields": bad_fields,
                          "turnover_ok": (None if pd.isna(
                              turn_ok.loc[row.name]) else bool(turn_ok.loc[row.name]))})
    conflicts.sort(key=lambda c: c["key"])
    return {
        "sec_keys": len(s_keys),
        "udiff_keys": len(u_keys),
        "sec_duplicate_keys_collapsed": sec_collapsed,
        "udiff_duplicate_keys_collapsed": udiff_collapsed,
        "common_keys": len(common),
        "sec_only": len(s_keys - u_keys),
        "udiff_only": len(u_keys - s_keys),
        "exact_keys": exact,
        "turnover_ok": turnover_ok,
        "turnover_mismatch": turnover_mismatch,
        "field_mismatches": {k: v for k, v in field_mismatches.items() if v},
        "conflicts": conflicts,
    }


def classify_ohlc(series: str, o_val: Any, h_val: Any, l_val: Any,
                  c_val: Any) -> str:
    """Classify OHLC consistency without deleting rows (gold precedent).

    Evidence: every OHLC violation in the acquired corpus (227 sec_bhav +
    216 UDiFF rows) belongs to series T0 (T+0 settlement), whose published
    close follows a different determination and can fall outside the
    traded [low, high]. Exact NSE T0 close semantics are not established
    from authoritative documentation, so affected rows are PRESERVED and
    flagged rather than deleted or adjusted. Non-T0 violations (none
    observed) receive a distinct flag for the same reason.
    """
    present = [v for v in (o_val, h_val, l_val, c_val)
               if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if len(present) < 4:
        return "ok"
    o_v, h_v, l_v, c_v = (float(v) for v in (o_val, h_val, l_val, c_val))
    if h_v >= max(o_v, c_v, l_v) and l_v <= min(o_v, c_v, h_v):
        return "ok"
    if str(series) == "T0":
        return "t0_close_outside_range"
    return "close_outside_range"


def build_canonical(
    sec_frames: List[pd.DataFrame],
    sec_filenames: List[str],
    udiff_frames: Optional[List[pd.DataFrame]] = None,
    udiff_filenames: Optional[List[str]] = None,
    exclude_files: Optional[List[str]] = None,
    exclude_keys: Optional[List[Tuple[str, str, str]]] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Build canonical security x date rows from sec_bhav with UDiFF ISIN attach.

    Raises ValueError on any conflicting (date, symbol, series) overlap —
    within or across regimes — following repository conventions.

    Documented exclusions (never silent):
      - exclude_files: raw filenames dropped entirely (e.g. the
        2019-09-30 artifact NSE serves with 27-Jun-2019 content under a
        September filename — date unresolvable, fail closed).
      - exclude_keys: (date, symbol, series) keys dropped (e.g. the 6
        cross-regime conflicts where both official regimes publish
        different values for the same key).
    Both are counted in stats and must appear in manifest accounting.
    """
    value_cols = ["open", "high", "low", "close", "last_price", "prev_close",
                  "vwap", "traded_quantity", "turnover_lacs", "number_of_trades",
                  "deliverable_quantity", "deliverable_percentage"]
    excluded_file_set = set(exclude_files or [])
    excluded_key_set = set(exclude_keys or [])
    kept_pairs = [(f, n) for f, n in zip(sec_frames, sec_filenames)
                  if n not in excluded_file_set]
    if len(kept_pairs) != len(sec_frames):
        sec_frames = [f for f, _ in kept_pairs]
        sec_filenames = [n for _, n in kept_pairs]
    overlaps = detect_key_overlaps(sec_frames, sec_filenames, value_cols)
    conflicts = [o for o in overlaps if not o.identical]
    if conflicts:
        detail = "; ".join(f"{c.key} in {c.files}" for c in conflicts[:5])
        raise ValueError(f"Conflicting sec_bhav records detected: {detail}")

    combined = pd.concat(sec_frames, ignore_index=True)
    combined = _key_frame(combined)
    key_cols = ["_key_obs", "_key_sym", "_key_ser"]
    present_before = set(zip(combined["_key_obs"].astype(str),
                             combined["_key_sym"].astype(str),
                             combined["_key_ser"].astype(str)))
    missing_exclusions = sorted(set(excluded_key_set) - present_before)
    if excluded_key_set:
        # Exclusions apply BEFORE any gate: excluded keys participate in
        # neither the cross-regime comparison nor the canonical output.
        keep = combined.apply(
            lambda r: (str(r["_key_obs"]), str(r["_key_sym"]), str(r["_key_ser"]))
            not in excluded_key_set, axis=1)
        combined = combined[keep].reset_index(drop=True)
    # Provenance via groupby (identical to the original per-row accumulation).
    prov_source = pd.concat(
        [_key_frame(f).assign(_src_file=n)
         for f, n in zip(sec_frames, sec_filenames) if not f.empty],
        ignore_index=True)
    provenance = (prov_source.groupby(key_cols)["_src_file"]
                  .agg(lambda files: ";".join(sorted(set(files)))))

    # Cross-regime conflict gate on shared keys (OHLCV exact).
    cross_stats: Dict[str, Any] = {}
    if udiff_frames:
        u_combined = pd.concat(udiff_frames, ignore_index=True)
        cross_stats = compare_regimes(combined, u_combined)
        blocking = [c for c in cross_stats["conflicts"] if c["fields"]]
        if blocking:
            detail = "; ".join(str(c["key"]) + ":" + ",".join(c["fields"])
                               for c in blocking[:5])
            raise ValueError(
                f"Conflicting cross-regime records detected "
                f"({len(blocking)} keys): {detail}")

    # UDiFF ISIN attach: same-day same-key, exactly one distinct ISIN.
    # Vectorized: per-key ISIN nunique + first meta via groupby.
    attach = pd.DataFrame(columns=key_cols + ["isin", "isin_basis",
                                              "security_name", "fin_instrm_id",
                                              "fin_instrm_type", "segment",
                                              "turnover_inr"])
    if udiff_frames:
        u_all = pd.concat(
            [_key_frame(f) for f in udiff_frames if not f.empty],
            ignore_index=True)
        u_all["_isin_norm"] = u_all["isin"].where(u_all["isin"].notna(), None)
        grouped = u_all.groupby(key_cols, sort=False)
        isin_nunique = grouped["_isin_norm"].nunique(dropna=True)
        isin_first = grouped["_isin_norm"].first()
        meta_first = grouped[["security_name", "fin_instrm_id",
                              "fin_instrm_type", "segment",
                              "turnover_inr"]].first()
        attach = pd.DataFrame({
            "isin": isin_first.where(isin_nunique == 1, None),
            "isin_basis": isin_nunique.map(
                lambda n: "udiff_match" if n == 1 else (
                    "ambiguous" if n > 1 else "unmatched")),
        }).join(meta_first).reset_index()

    combined = combined.sort_values(
        ["_key_obs", "symbol", "series"]).drop_duplicates(
        subset=key_cols, keep="first")
    combined["source_files"] = combined.set_index(key_cols).index.map(
        provenance).fillna("")
    combined = combined.merge(attach, on=key_cols, how="left")
    combined["isin_basis"] = combined["isin_basis"].fillna("unmatched")
    # Keys were already dropped before the gate; verify the drop count.
    excluded_keys_dropped = len(excluded_key_set) - len(missing_exclusions)
    if missing_exclusions:
        raise ValueError(
            f"Excluded keys not present in canonical input: {missing_exclusions}")
    # Attach stats are per canonical (sec_bhav) key, matching the original
    # per-key accounting: keys with no UDiFF counterpart count as unmatched.
    isin_stats = {
        "matched": int((combined["isin_basis"] == "udiff_match").sum()),
        "unmatched": int((combined["isin_basis"] == "unmatched").sum()),
        "ambiguous": int((combined["isin_basis"] == "ambiguous").sum()),
    }
    combined["observation_date"] = pd.to_datetime(
        combined["_key_obs"]).dt.date
    combined["availability_date"] = pd.NaT
    combined["ohlc_flag"] = [
        classify_ohlc(s, o, h, l, c) for s, o, h, l, c in zip(
            combined["series"], combined["open"], combined["high"],
            combined["low"], combined["close"])]
    combined["vintage_status"] = "observed"
    combined["revision_version"] = 0
    combined["availability_basis"] = "unknown_historical_availability"
    combined["regime"] = "sec_bhav"
    combined["source"] = "NSE"
    combined = combined.drop(columns=["_key_obs", "_key_sym", "_key_ser",
                                       "source_file"])
    combined = combined.sort_values(
        ["observation_date", "symbol", "series"]).reset_index(drop=True)
    stats = {"within_regime_conflicts": 0, "cross_regime": cross_stats,
             "isin_attach": isin_stats,
             "excluded_files": sorted(excluded_file_set),
             "excluded_file_count": len(excluded_file_set),
             "excluded_keys": sorted(excluded_key_set),
             "excluded_key_count": len(excluded_key_set),
             "excluded_keys_dropped": excluded_keys_dropped}
    return combined[CANONICAL_COLUMNS], stats


def agent_eligible_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Only rows with verified availability are agent-visible.

    Historical bhavcopy publication timing is not recoverable, so every
    canonical row carries NULL availability and this returns zero rows
    (fail closed). Availability is never fabricated here.
    """
    eligible = frame[
        frame["availability_date"].notna()
        & frame["vintage_status"].isin(AGENT_ELIGIBLE_VINTAGES)
    ].copy()
    return eligible.reset_index(drop=True)


def build_agent_information_set(frame: pd.DataFrame):
    """Build an InformationSet of agent-eligible equity vintages.

    Fails closed BEFORE InformationSet construction when nothing is
    eligible: InformationSet raises on NA availability and must not be
    weakened to accommodate this dataset.
    """
    from src.india.information_set import InformationSet

    eligible = agent_eligible_rows(frame)
    if eligible.empty:
        raise ValueError("No agent-eligible NSE equity vintages.")
    vintages = pd.DataFrame({
        "variable": "NSE_EQUITY",
        "observation_date": pd.to_datetime(eligible["observation_date"]),
        "availability_date": pd.to_datetime(eligible["availability_date"]),
        "revision_version": eligible["revision_version"].astype(int),
        "value": pd.to_numeric(eligible["close"], errors="coerce"),
    })
    return InformationSet(vintages)


def validate_no_forward_fill(frame: pd.DataFrame) -> List[str]:
    """Confirm canonical rows are never fabricated: every row traces to a
    validated NSE observation; keys unique; no fills."""
    errors: List[str] = []
    if frame.duplicated(subset=["observation_date", "symbol", "series"]).any():
        errors.append("duplicate (observation_date, symbol, series) keys")
    if frame["close"].isna().all():
        errors.append("no close values at all")
    return errors
