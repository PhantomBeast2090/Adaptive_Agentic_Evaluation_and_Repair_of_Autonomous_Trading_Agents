"""RBI USD/INR Reference Rate Acquisition Adapter.

PRIMARY SOURCE: Reserve Bank of India — FBIL (Financial Benchmarks India)
  or RBI DBIE reference rates

USD/INR RATE SOURCE HIERARCHY:
  1. FBIL Reference Rate (most official, published daily)
     https://www.fbil.org.in/#/home → USD/INR Reference Rate
  2. RBI DBIE Reference Rate
     https://dbie.rbi.org.in/ → External Sector → Exchange Rates
  3. RBI published data
     https://www.rbi.org.in/scripts/ReferenceRateArchive.aspx

The RBI/FBIL reference rate is the official interbank reference rate for
INR-USD, published each working day at approximately 13:30 IST.

AUTOMATION STATUS:
  RBI Reference Rate archive page allows historical downloads but requires
  web navigation. FBIL may have a data API.

MANUAL DOWNLOAD INSTRUCTIONS:
  Option A (RBI Reference Rate Archive):
  1. Visit: https://www.rbi.org.in/scripts/ReferenceRateArchive.aspx
  2. Select date range
  3. Download / export data
  4. Place at: data/raw/india/currency/usd_inr_daily.csv

  Option B (FBIL):
  1. Visit: https://www.fbil.org.in/#/home
  2. Select Benchmark Rates → USD/INR Reference Rate
  3. Download historical data
  4. Place at: data/raw/india/currency/usd_inr_daily.csv

  Option C (RBI DBIE):
  1. Visit: https://dbie.rbi.org.in/
  2. Navigate: External Sector → Exchange Rates → USD/INR
  3. Download as CSV
  4. Place at: data/raw/india/currency/usd_inr_daily.csv

EXPECTED COLUMNS:
  Date | USD/INR rate (or: Date | Currency | Rate)

EXPECTED COVERAGE:
  RBI reference rates available from approximately 2000.
  Note: "expected" ≠ "verified" — coverage audit determines actual coverage.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd
import requests

from data.acquisition.base import AcquisitionError, BaseAdapter
from src.schemas.india_data import (
    DataFrequency,
    DataTier,
)

_RBI_REFERENCE_RATE_URL = (
    "https://www.rbi.org.in/scripts/ReferenceRateArchive.aspx"
)


class RBICurrencyAdapter(BaseAdapter):
    """Acquire USD/INR official reference rate from RBI/FBIL."""

    MANUAL_DOWNLOAD_INSTRUCTIONS = """
USD/INR Official Rate Manual Download:

Option A — RBI Reference Rate Archive (preferred):
  1. Visit: https://www.rbi.org.in/scripts/ReferenceRateArchive.aspx
  2. Select the widest available date range
  3. Click "Get Data" then download/export
  4. Place at: data/raw/india/currency/usd_inr_daily.csv

Option B — FBIL USD/INR:
  1. Visit: https://www.fbil.org.in/#/home
  2. Navigate to Benchmark Rates → Reference Rates
  3. Download USD/INR Reference Rate historical data
  4. Place at: data/raw/india/currency/usd_inr_daily.csv

Option C — RBI DBIE:
  1. Visit: https://dbie.rbi.org.in/
  2. Navigate: External Sector → Exchange Rates → Spot Rate (USD/INR)
  3. Download as CSV
  4. Place at: data/raw/india/currency/usd_inr_daily.csv

Expected minimum columns:
  Date | USD/INR (INR per 1 USD)

Note: This MUST be the official RBI/FBIL reference rate.
Do NOT use retail/commercial bank rates or Yahoo Finance as primary source.
"""

    @property
    def dataset_id(self) -> str:
        return "rbi_usd_inr_daily"

    @property
    def tier(self) -> DataTier:
        return DataTier.A

    @property
    def asset_class(self) -> str:
        return "currency"

    @property
    def variable(self) -> str:
        return "USD_INR_DAILY"

    @property
    def source_institution(self) -> str:
        return "RBI"

    @property
    def frequency(self) -> DataFrequency:
        return DataFrequency.DAILY

    @property
    def raw_output_dir(self) -> Path:
        return self.base_dir / "data" / "raw" / "india" / "currency"

    def acquire(self) -> Path:
        output_path = self.raw_output_dir / "usd_inr_daily.csv"

        if output_path.exists() and output_path.stat().st_size > 500:
            self.logger.info(f"USD/INR file already present: {output_path}")
            return output_path

        raise AcquisitionError(
            dataset_id=self.dataset_id,
            source="RBI Reference Rate Archive / FBIL",
            reason=(
                "RBI Reference Rate Archive requires web form interaction "
                "not reliably automatable. FBIL may require API key. "
                "Manual download required."
            ),
            manual_instructions=self.MANUAL_DOWNLOAD_INSTRUCTIONS,
        )

    def validate(self, raw_path: Path) -> List[str]:
        errors = self._require_non_empty(raw_path)
        if errors:
            return errors

        try:
            df = pd.read_csv(raw_path, nrows=10)
        except Exception as e:
            return [f"Cannot read CSV: {e}"]

        # Need a date-like and a rate column
        date_found = any("date" in c.lower() for c in df.columns)
        rate_found = any(
            any(k in c.lower() for k in ["usd", "inr", "rate", "rs.", "rupee"])
            for c in df.columns
        )
        if not date_found:
            errors.append(f"No date column found. Columns: {list(df.columns)}")
        if not rate_found:
            errors.append(f"No rate/USD/INR column found. Columns: {list(df.columns)}")

        return errors

    def load_normalized(self) -> pd.DataFrame:
        """Load and normalise USD/INR CSV.

        Returns DataFrame with columns: date, rate (INR per USD), source, frequency
        """
        raw_path = self.raw_output_dir / "usd_inr_daily.csv"
        if not raw_path.exists():
            raise FileNotFoundError(
                f"USD/INR file not found: {raw_path}\n"
                f"{self.MANUAL_DOWNLOAD_INSTRUCTIONS}"
            )

        df = pd.read_csv(raw_path)
        df.columns = [c.strip() for c in df.columns]

        # Find date column
        date_col = next(
            (c for c in df.columns if "date" in c.lower()), df.columns[0]
        )

        # Find rate column
        rate_col = next(
            (c for c in df.columns
             if any(k in c.lower() for k in
                    ["usd/inr", "usd inr", "inr", "rate", "rs.", "rupee", "usd"])),
            df.columns[1] if len(df.columns) > 1 else None,
        )

        df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce")
        df = df.dropna(subset=[date_col])

        result = pd.DataFrame({
            "date": df[date_col],
            "rate": pd.to_numeric(df[rate_col], errors="coerce") if rate_col else None,
            "source": "RBI_REFERENCE_RATE",
            "frequency": "daily",
            "is_reference_rate": True,
        })

        result = result.sort_values("date").reset_index(drop=True)
        return result
