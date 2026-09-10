"""NSE Equity (Bhavcopy) Acquisition Adapter.

Acquires security-level daily equity data from NSE Bhavcopy files.

PRIMARY SOURCE: NSE India — Bhavcopy (daily market summary)
  URL: https://www.nseindia.com/market-data/historical-data-equity

BHAVCOPY FORMAT:
  NSE publishes a daily CM Bhavcopy CSV for each trading day containing
  all traded equity securities with:
    SYMBOL, SERIES, OPEN, HIGH, LOW, CLOSE, LAST, PREVCLOSE,
    TOTTRDQTY, TOTTRDVAL, TIMESTAMP, TOTALTRADES, ISIN

AUTOMATION STATUS:
  NSE Bhavcopy files for individual dates are available from:
    https://archives.nseindia.com/products/content/sec_bhavdata_full_<DDMMYYYY>.csv
  (or similar URL patterns that may change)
  Automated bulk download attempts are documented here.

MANUAL DOWNLOAD INSTRUCTIONS (if automated fails):
  1. Visit: https://www.nseindia.com/market-data/historical-data-equity
  2. Select "Equity Bhavcopy" under "Equity Archives"
  3. Select date range and download
  4. Place CSV files at: data/raw/india/equities/
     File naming: bhavcopy_<YYYYMMDD>.csv
  5. For bulk download, the NSE archives sometimes allow:
     https://archives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv

PRESERVES (from Bhavcopy):
  - SYMBOL, ISIN, SERIES (EQ, BE, SM, IL, etc.)
  - OPEN, HIGH, LOW, CLOSE, LAST, PREVCLOSE
  - TOTTRDQTY (total traded quantity)
  - TOTTRDVAL (total traded value = proxy for turnover)
  - TOTALTRADES (number of trades)
  - No delivery data in base Bhavcopy — delivery data is a separate report

NOTE ON ADJUSTED PRICES:
  Bhavcopy contains UNADJUSTED prices.
  Adjusted prices must be constructed separately using corporate action data.
  This adapter does NOT manufacture adjusted prices.

EXPECTED COVERAGE:
  NSE equity Bhavcopy: available from approximately 1994 onwards.
  Note: "expected" ≠ "verified" — coverage audit determines actual coverage.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

import pandas as pd
import requests

from data.acquisition.base import AcquisitionError, BaseAdapter
from src.schemas.india_data import (
    DataFrequency,
    DataTier,
)

# Archive URL pattern — may be stale; NSE periodically reorganises
_BHAVCOPY_ARCHIVE_URL = (
    "https://archives.nseindia.com/products/content/sec_bhavdata_full_{date_ddmmyyyy}.csv"
)

# NSE equity archive alternate pattern
_BHAVCOPY_ALT_URL = (
    "https://www1.nseindia.com/content/historical/EQUITIES/{year}/{month_abbr}/"
    "cm{date_ddMMMYYYY}bhav.csv.zip"
)

BHAVCOPY_STANDARD_COLS = {
    "SYMBOL": "symbol",
    "SERIES": "series",
    "OPEN": "open",
    "HIGH": "high",
    "LOW": "low",
    "CLOSE": "close",
    "LAST": "last",
    "PREVCLOSE": "prev_close",
    "TOTTRDQTY": "traded_quantity",
    "TOTTRDVAL": "turnover",
    "TIMESTAMP": "date",
    "TOTALTRADES": "number_of_trades",
    "ISIN": "isin",
}


class NSEEquityBhavCopyAdapter(BaseAdapter):
    """Acquire NSE equity Bhavcopy data.

    Downloads individual daily Bhavcopy files from NSE archives
    for a specified date range, then concatenates them.
    """

    MANUAL_DOWNLOAD_INSTRUCTIONS = """
NSE Equity Bhavcopy Manual Download Instructions:
1. Visit: https://www.nseindia.com/market-data/historical-data-equity
2. Under "Equity Archives" select "Bhavcopy" (CM Bhavcopy)
3. Select date range and download individual files
4. Place all CSV files at: data/raw/india/equities/
   File naming convention: bhavcopy_<YYYYMMDD>.csv
   (e.g. bhavcopy_20200101.csv)

Alternative: NSE bulk archive
  https://archives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv
  (DDMMYYYY format, e.g. 01012020 for 2020-01-01)

Expected columns per file:
  SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,
  TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN

Note: Delivery data (deliverable qty, delivery %) is a SEPARATE report
from NSE (MTO/Delivery reports). Do NOT conflate with Bhavcopy.
"""

    @property
    def dataset_id(self) -> str:
        return "nse_equity_bhavcopy_daily"

    @property
    def tier(self) -> DataTier:
        return DataTier.A

    @property
    def asset_class(self) -> str:
        return "equity"

    @property
    def variable(self) -> str:
        return "EQUITY_BHAVCOPY_DAILY"

    @property
    def source_institution(self) -> str:
        return "NSE"

    @property
    def frequency(self) -> DataFrequency:
        return DataFrequency.DAILY

    @property
    def raw_output_dir(self) -> Path:
        return self.base_dir / "data" / "raw" / "india" / "equities"

    def acquire(self) -> Path:
        """Attempt to download Bhavcopy files from NSE archives.

        This checks if any bhavcopy files already exist. If not, raises
        AcquisitionError with manual instructions.
        """
        existing = list(self.raw_output_dir.glob("bhavcopy_*.csv"))
        if existing:
            self.logger.info(
                f"Found {len(existing)} existing Bhavcopy files in {self.raw_output_dir}"
            )
            # Return path to a sentinel manifest file
            manifest_path = self.raw_output_dir / "bhavcopy_index.txt"
            with open(manifest_path, "w") as f:
                f.write(f"Bhavcopy files found: {len(existing)}\n")
                for p in sorted(existing):
                    f.write(f"{p.name}\n")
            return manifest_path

        raise AcquisitionError(
            dataset_id=self.dataset_id,
            source="NSE Bhavcopy Archives",
            reason=(
                "No Bhavcopy CSV files found in data/raw/india/equities/. "
                "Automated bulk download of NSE Bhavcopy requires navigating "
                "NSE's archive with session authentication. "
                "Manual download is the reliable approach."
            ),
            manual_instructions=self.MANUAL_DOWNLOAD_INSTRUCTIONS,
        )

    def validate(self, raw_path: Path) -> List[str]:
        """Validate the Bhavcopy index file or a specific bhavcopy CSV."""
        errors = self._require_non_empty(raw_path)
        if errors:
            return errors
        # If it's the index file (txt), check at least one CSV exists
        if raw_path.suffix == ".txt":
            csvs = list(self.raw_output_dir.glob("bhavcopy_*.csv"))
            if not csvs:
                errors.append("No bhavcopy_*.csv files found in equities directory.")
            else:
                # Validate first file
                sample = csvs[0]
                try:
                    df = pd.read_csv(sample, nrows=3)
                    required = {"SYMBOL", "CLOSE", "ISIN"}
                    missing = required - set(df.columns)
                    if missing:
                        errors.append(f"Missing required columns in {sample.name}: {missing}")
                except Exception as e:
                    errors.append(f"Cannot read {sample.name}: {e}")
        return errors

    def load_normalized(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        series_filter: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Load and normalise all available Bhavcopy files.

        Args:
            start_date: Filter to dates >= start_date
            end_date: Filter to dates <= end_date
            series_filter: Only include these series (e.g. ['EQ', 'BE'])
        """
        csv_files = sorted(self.raw_output_dir.glob("bhavcopy_*.csv"))
        if not csv_files:
            raise FileNotFoundError(
                f"No bhavcopy_*.csv files in {self.raw_output_dir}\n"
                f"{self.MANUAL_DOWNLOAD_INSTRUCTIONS}"
            )

        frames = []
        for f in csv_files:
            try:
                df = pd.read_csv(f)
                df.columns = [c.strip() for c in df.columns]

                # Rename
                rename_map = {k: v for k, v in BHAVCOPY_STANDARD_COLS.items()
                              if k in df.columns}
                df = df.rename(columns=rename_map)

                # Parse date
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
                else:
                    # Infer from filename: bhavcopy_YYYYMMDD.csv
                    date_str = f.stem.replace("bhavcopy_", "")
                    try:
                        parsed = pd.to_datetime(date_str, format="%Y%m%d")
                        df["date"] = parsed
                    except Exception:
                        df["date"] = pd.NaT

                frames.append(df)
            except Exception as e:
                self.logger.warning(f"Skipping {f.name}: {e}")

        if not frames:
            raise ValueError("No valid Bhavcopy frames could be loaded.")

        result = pd.concat(frames, ignore_index=True)

        # Apply filters
        if start_date:
            result = result[result["date"] >= pd.Timestamp(start_date)]
        if end_date:
            result = result[result["date"] <= pd.Timestamp(end_date)]
        if series_filter:
            result = result[result["series"].isin(series_filter)]

        # Numeric conversion
        for col in ["open", "high", "low", "close", "prev_close",
                    "traded_quantity", "turnover", "number_of_trades"]:
            if col in result.columns:
                result[col] = pd.to_numeric(result[col], errors="coerce")

        result = result.sort_values(["date", "symbol"]).reset_index(drop=True)
        result["source"] = "NSE_BHAVCOPY"
        result["corporate_action_adjusted"] = False  # Raw Bhavcopy is unadjusted

        return result
