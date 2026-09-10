"""NSE Index Data Acquisition Adapter.

Fetches historical data for:
  - NIFTY 50
  - NIFTY 500
  - NIFTY BANK
  - NIFTY IT
  - NIFTY PHARMA
  - India VIX (separate file)

PRIMARY SOURCE: NSE India official historical data
  NSE Index data: https://www.nseindia.com/market-data/live-equity-market
  NSE VIX: https://www.nseindia.com/market-data/india-vix

AUTOMATION STATUS:
  NSE's website uses Cloudflare protection and requires session cookies.
  Fully automated headless download is NOT reliably possible as of 2024.

  Strategy:
    1. Attempt automated fetch using requests + session headers
    2. If blocked (403/Cloudflare), register as PENDING_MANUAL_DOWNLOAD
       and print clear instructions for the researcher

MANUAL DOWNLOAD INSTRUCTIONS (if automation fails):
  1. Visit https://www.nseindia.com/market-data/historical-index-data
  2. Select index (e.g. NIFTY 50)
  3. Select "From Date" and "To Date" (use full history)
  4. Click "Download" → saves as CSV
  5. Place the CSV at: data/raw/india/indices/<index_name>_daily.csv
     e.g. data/raw/india/indices/nifty50_daily.csv
  For India VIX: https://www.nseindia.com/market-data/india-vix
     Place at: data/raw/india/india_vix/india_vix_daily.csv

EXPECTED COLUMNS (NSE index CSV format):
  Date, Open, High, Low, Close, Shares Traded, Turnover (Rs. Cr)
  (exact headers vary by download; adapter normalises them)

EXPECTED COVERAGE (from NSE published history):
  NIFTY 50: approximately from 1999-01-01
  India VIX: approximately from 2008-11-02
  NOTE: "expected" ≠ "verified" — coverage audit will determine actual coverage.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

from data.acquisition.base import AcquisitionError, BaseAdapter
from src.schemas.india_data import (
    AcquisitionStatus,
    DataFrequency,
    DataTier,
    ValidationStatus,
)

# NSE index historical data endpoints
# These may change; NSE periodically restructures their website
_NSE_INDEX_HISTORY_URL = (
    "https://www.nseindia.com/api/historical/indicesHistory"
    "?indexType={index_type}&from={from_date}&to={to_date}"
)

_NSE_VIX_HISTORY_URL = (
    "https://www.nseindia.com/api/historical/vixhistory"
    "?from={from_date}&to={to_date}"
)

_NSE_BASE_URL = "https://www.nseindia.com"

# Mapping from our canonical names to NSE index type identifiers
NSE_INDEX_MAP: Dict[str, str] = {
    "NIFTY_50": "NIFTY 50",
    "NIFTY_500": "NIFTY 500",
    "NIFTY_BANK": "NIFTY BANK",
    "NIFTY_IT": "NIFTY IT",
    "NIFTY_PHARMA": "NIFTY PHARMA",
    "NIFTY_FMCG": "NIFTY FMCG",
    "NIFTY_AUTO": "NIFTY AUTO",
    "NIFTY_MIDCAP_100": "NIFTY MIDCAP 100",
    "NIFTY_SMALLCAP_100": "NIFTY SMALLCAP 100",
    "NIFTY_NEXT_50": "NIFTY NEXT 50",
}


# ---------------------------------------------------------------------------
# India VIX adapter
# ---------------------------------------------------------------------------

class IndiaVIXAdapter(BaseAdapter):
    """Acquire India VIX historical data from NSE."""

    dataset_id = "nse_india_vix_daily"
    tier = DataTier.B
    asset_class = "volatility_index"
    variable = "INDIA_VIX_DAILY"
    source_institution = "NSE"
    frequency = DataFrequency.DAILY
    source_url = "https://www.nseindia.com/market-data/india-vix"

    MANUAL_DOWNLOAD_INSTRUCTIONS = """
India VIX Manual Download Instructions:
1. Visit: https://www.nseindia.com/market-data/india-vix
2. Click "Historical Data" tab
3. Select the widest available date range
4. Download as CSV
5. Place the file at:
   data/raw/india/india_vix/india_vix_daily.csv

Expected columns (NSE VIX CSV):
  Date | Open | High | Low | Close | Previous Close | Change | % Change

Note: India VIX history starts approximately from 2008-11-02.
"""

    EXPECTED_COLUMNS_RAW = {
        "Date", "Open", "High", "Low", "Close",
        "Previous Close", "Change", "% Change"
    }

    NORMALIZED_COLUMNS = {
        "Date": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Previous Close": "prev_close",
        "Change": "change",
        "% Change": "pct_change",
    }

    @property
    def raw_output_dir(self) -> Path:
        return self.base_dir / "data" / "raw" / "india" / "india_vix"

    def acquire(self) -> Path:
        """Attempt automated NSE VIX download, fall back to manual instructions."""
        output_path = self.raw_output_dir / "india_vix_daily.csv"

        # Check if already manually placed
        if output_path.exists() and output_path.stat().st_size > 1000:
            self.logger.info(f"India VIX file already present: {output_path}")
            return output_path

        # Attempt automated fetch
        try:
            df = self._fetch_via_nse_api()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(output_path, index=False)
            self.logger.info(
                f"India VIX fetched via NSE API: {len(df)} rows → {output_path}"
            )
            return output_path
        except Exception as e:
            raise AcquisitionError(
                dataset_id=self.dataset_id,
                source=self.source_url,
                reason=(
                    f"Automated NSE VIX fetch failed: {e}. "
                    "NSE website requires session authentication that is not "
                    "reliably automated. Manual download required."
                ),
                manual_instructions=self.MANUAL_DOWNLOAD_INSTRUCTIONS,
            )

    def _fetch_via_nse_api(self) -> pd.DataFrame:
        """Attempt to fetch India VIX data via NSE API with session setup."""
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/",
        })

        # Establish session cookies by visiting main page
        resp = session.get(_NSE_BASE_URL, timeout=15)
        if resp.status_code != 200:
            raise Exception(f"NSE base page returned {resp.status_code}")
        time.sleep(1)

        # Attempt VIX API (date range: max available)
        url = _NSE_VIX_HISTORY_URL.format(
            from_date="02-11-2008", to_date="31-12-2024"
        )
        resp = session.get(url, timeout=30)
        if resp.status_code != 200:
            raise Exception(
                f"NSE VIX API returned {resp.status_code}. "
                "This often indicates Cloudflare blocking or session expiry."
            )

        data = resp.json()
        if "data" not in data:
            raise Exception(f"Unexpected NSE VIX API response structure: {list(data.keys())}")

        records = data["data"]
        if not records:
            raise Exception("NSE VIX API returned empty data array.")

        df = pd.DataFrame(records)
        return df

    def validate(self, raw_path: Path) -> List[str]:
        """Validate India VIX CSV."""
        errors = self._require_non_empty(raw_path)
        if errors:
            return errors

        try:
            df = pd.read_csv(raw_path, nrows=5)
        except Exception as e:
            return [f"Cannot read CSV: {e}"]

        # Check for close/Close column
        close_candidates = [c for c in df.columns if "close" in c.lower() or "Close" in c]
        if not close_candidates:
            errors.append(f"No 'Close' column found. Available: {list(df.columns)}")

        date_candidates = [c for c in df.columns if "date" in c.lower() or "Date" in c]
        if not date_candidates:
            errors.append(f"No 'Date' column found. Available: {list(df.columns)}")

        return errors

    def load_normalized(self) -> pd.DataFrame:
        """Load and normalise a manually downloaded India VIX CSV.

        Returns a DataFrame with standardized column names and DatetimeIndex.
        """
        raw_path = self.raw_output_dir / "india_vix_daily.csv"
        if not raw_path.exists():
            raise FileNotFoundError(
                f"India VIX raw file not found: {raw_path}\n"
                f"{self.MANUAL_DOWNLOAD_INSTRUCTIONS}"
            )

        df = pd.read_csv(raw_path)
        df.columns = [c.strip() for c in df.columns]

        # Rename columns using known mapping (case-insensitive partial match)
        rename_map = {}
        for raw_col in df.columns:
            for expected, normal in self.NORMALIZED_COLUMNS.items():
                if raw_col.strip().lower() == expected.lower():
                    rename_map[raw_col] = normal
        df = df.rename(columns=rename_map)

        # Parse date
        date_col = "date" if "date" in df.columns else df.columns[0]
        df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce")
        df = df.dropna(subset=[date_col])
        df = df.set_index(date_col).sort_index()

        # Convert numeric columns
        for col in ["open", "high", "low", "close", "prev_close", "change", "pct_change"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df


# ---------------------------------------------------------------------------
# NIFTY Index adapter
# ---------------------------------------------------------------------------

class NSEIndexAdapter(BaseAdapter):
    """Acquire NSE index historical data (NIFTY 50, NIFTY 500, etc.)."""

    def __init__(self, index_key: str, base_dir: str = "."):
        super().__init__(base_dir)
        if index_key not in NSE_INDEX_MAP:
            raise ValueError(
                f"Unknown index key '{index_key}'. "
                f"Supported: {list(NSE_INDEX_MAP.keys())}"
            )
        self._index_key = index_key
        self._index_nse_name = NSE_INDEX_MAP[index_key]
        self._filename = f"{index_key.lower()}_daily.csv"

    @property
    def dataset_id(self) -> str:
        return f"nse_{self._index_key.lower()}_daily"

    @property
    def tier(self) -> DataTier:
        return DataTier.A

    @property
    def asset_class(self) -> str:
        return "index"

    @property
    def variable(self) -> str:
        return f"{self._index_key}_DAILY"

    @property
    def source_institution(self) -> str:
        return "NSE"

    @property
    def frequency(self) -> DataFrequency:
        return DataFrequency.DAILY

    @property
    def raw_output_dir(self) -> Path:
        return self.base_dir / "data" / "raw" / "india" / "indices"

    @property
    def manual_download_instructions(self) -> str:
        return f"""
NSE Index '{self._index_nse_name}' Manual Download Instructions:
1. Visit: https://www.nseindia.com/market-data/historical-index-data
2. In the "Select Index" dropdown, choose: {self._index_nse_name}
3. In "From Date" enter the earliest available date
4. In "To Date" enter today's date
5. Click "Get Data", then "Download CSV"
6. Place the downloaded file at:
   data/raw/india/indices/{self._filename}

Expected columns (NSE format):
  Date | Open | High | Low | Close | Shares Traded | Turnover (Rs. Cr)

Note: NSE historical index data typically starts from:
  NIFTY 50: ~1999-01-04
  NIFTY 500: ~1995-01-01
  NIFTY BANK: ~2000-01-04
  NIFTY IT, PHARMA, etc.: varies
"""

    def acquire(self) -> Path:
        output_path = self.raw_output_dir / self._filename

        if output_path.exists() and output_path.stat().st_size > 1000:
            self.logger.info(f"{self._index_key} file already present: {output_path}")
            return output_path

        raise AcquisitionError(
            dataset_id=self.dataset_id,
            source=f"NSE historical data for {self._index_nse_name}",
            reason=(
                "Automated NSE index download requires session authentication "
                "not reliably automatable via HTTP. Manual download required."
            ),
            manual_instructions=self.manual_download_instructions,
        )

    def validate(self, raw_path: Path) -> List[str]:
        errors = self._require_non_empty(raw_path)
        if errors:
            return errors

        try:
            df = pd.read_csv(raw_path, nrows=5)
        except Exception as e:
            return [f"Cannot read CSV: {e}"]

        close_candidates = [c for c in df.columns if "close" in c.lower()]
        if not close_candidates:
            errors.append(f"No 'Close' column. Columns: {list(df.columns)}")

        date_candidates = [c for c in df.columns if "date" in c.lower()]
        if not date_candidates:
            errors.append(f"No 'Date' column. Columns: {list(df.columns)}")

        return errors

    def load_normalized(self) -> pd.DataFrame:
        """Load and normalise a manually downloaded NSE index CSV."""
        raw_path = self.raw_output_dir / self._filename
        if not raw_path.exists():
            raise FileNotFoundError(
                f"Index file not found: {raw_path}\n"
                f"{self.manual_download_instructions}"
            )

        df = pd.read_csv(raw_path)
        df.columns = [c.strip() for c in df.columns]

        # Normalise common NSE column name patterns
        col_map = {}
        for c in df.columns:
            cl = c.lower().strip()
            if cl == "date":
                col_map[c] = "date"
            elif cl == "open":
                col_map[c] = "open"
            elif cl == "high":
                col_map[c] = "high"
            elif cl == "low":
                col_map[c] = "low"
            elif cl == "close":
                col_map[c] = "close"
            elif "shares traded" in cl or "volume" in cl:
                col_map[c] = "volume"
            elif "turnover" in cl:
                col_map[c] = "turnover"
            elif "pe" in cl:
                col_map[c] = "pe_ratio"
            elif "pb" in cl:
                col_map[c] = "pb_ratio"

        df = df.rename(columns=col_map)

        date_col = "date" if "date" in df.columns else df.columns[0]
        df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce")
        df = df.dropna(subset=[date_col])
        df["index_name"] = self._index_nse_name
        df = df.set_index(date_col).sort_index()

        for col in ["open", "high", "low", "close", "volume", "turnover"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df
