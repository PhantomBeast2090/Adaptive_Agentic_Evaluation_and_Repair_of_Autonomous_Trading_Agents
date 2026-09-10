"""Crude Oil Exogenous Context Acquisition Adapter.

NOTE ON SOURCE:
  Crude oil is EXOGENOUS CONTEXT — it is NOT an Indian tradable asset.
  It is included as an environmental variable that influences Indian markets.

  MCX does trade crude oil futures (MCX CRUDEOIL), but for exogenous
  context, the international benchmark (Brent/WTI) is more relevant.

SOURCE HIERARCHY:
  1. EIA (U.S. Energy Information Administration) — free, stable API
     https://www.eia.gov/petroleum/
  2. ICE (Intercontinental Exchange) — Brent Crude
  3. FRED (St. Louis Fed) — carries WTI daily series (DCOILWTICO)
     https://fred.stlouisfed.org/series/DCOILWTICO

  The EIA/FRED sources are explicitly documented as non-Indian.
  This is INTENTIONAL and MUST be noted in the manifest.

  If MCX crude oil futures are preferred (to use Indian market pricing),
  the MCX adapter pattern can be used similarly to gold.

AUTOMATION:
  FRED API is publicly accessible and can be automated.
  EIA API requires a free API key: https://www.eia.gov/opendata/

MANUAL DOWNLOAD INSTRUCTIONS:
  Option A (FRED — recommended for reproducibility):
  1. Visit: https://fred.stlouisfed.org/series/DCOILBRENTEU
     (or DCOILWTICO for WTI)
  2. Click "Download Data" → CSV
  3. Place at: data/raw/india/crude/brent_usd.csv

  Option B (EIA API):
  1. Get free API key: https://www.eia.gov/opendata/register.php
  2. Use endpoint: https://api.eia.gov/v2/petroleum/pri/spt/data/
  3. Place at: data/raw/india/crude/brent_usd.csv

EXPECTED COLUMNS:
  Date | Price (USD per barrel)

EXPECTED COVERAGE:
  Brent crude (FRED): from 1987
  WTI crude (FRED): from 1986
  Note: "expected" ≠ "verified" — coverage audit determines actual coverage.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import List

import pandas as pd
import requests

from data.acquisition.base import AcquisitionError, BaseAdapter
from src.schemas.india_data import (
    DataFrequency,
    DataTier,
)

# FRED series IDs
_FRED_BRENT_SERIES = "DCOILBRENTEU"
_FRED_WTI_SERIES = "DCOILWTICO"
_FRED_BASE_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


class CrudeOilContextAdapter(BaseAdapter):
    """Acquire crude oil price data as exogenous context.

    Source is explicitly non-Indian (FRED/EIA). This is documented
    in the manifest and cannot be silently changed.
    """

    MANUAL_DOWNLOAD_INSTRUCTIONS = """
Crude Oil (Exogenous Context) Manual Download:

Option A — FRED (recommended):
  1. Visit: https://fred.stlouisfed.org/series/DCOILBRENTEU
  2. Click "Download Data" → CSV
  3. Place at: data/raw/india/crude/brent_usd.csv

Option B — FRED WTI (alternative benchmark):
  1. Visit: https://fred.stlouisfed.org/series/DCOILWTICO
  2. Download as CSV
  3. Place at: data/raw/india/crude/wti_usd.csv

Note: Crude oil is EXOGENOUS CONTEXT only — it is not an Indian tradable
asset in this research environment. The source (FRED/EIA) is explicitly
non-Indian and this is intentional and documented.
"""

    def __init__(self, benchmark: str = "BRENT", base_dir: str = "."):
        super().__init__(base_dir)
        if benchmark not in ("BRENT", "WTI"):
            raise ValueError(f"Unknown benchmark '{benchmark}'. Use 'BRENT' or 'WTI'.")
        self._benchmark = benchmark
        self._fred_series = (
            _FRED_BRENT_SERIES if benchmark == "BRENT" else _FRED_WTI_SERIES
        )
        self._filename = f"{benchmark.lower()}_usd.csv"

    @property
    def dataset_id(self) -> str:
        return f"crude_oil_{self._benchmark.lower()}_daily"

    @property
    def tier(self) -> DataTier:
        return DataTier.C

    @property
    def asset_class(self) -> str:
        return "crude"

    @property
    def variable(self) -> str:
        return f"CRUDE_{self._benchmark}_USD_DAILY"

    @property
    def source_institution(self) -> str:
        return "FRED_EIA"

    @property
    def frequency(self) -> DataFrequency:
        return DataFrequency.DAILY

    @property
    def raw_output_dir(self) -> Path:
        return self.base_dir / "data" / "raw" / "india" / "crude"

    def acquire(self) -> Path:
        output_path = self.raw_output_dir / self._filename

        if output_path.exists() and output_path.stat().st_size > 1000:
            self.logger.info(f"Crude oil file already present: {output_path}")
            return output_path

        # Attempt FRED automated download
        try:
            df = self._fetch_from_fred()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(output_path, index=False)
            self.logger.info(
                f"Crude oil ({self._benchmark}) fetched from FRED: "
                f"{len(df)} rows → {output_path}"
            )
            return output_path
        except Exception as e:
            raise AcquisitionError(
                dataset_id=self.dataset_id,
                source=f"FRED ({self._fred_series})",
                reason=f"FRED automated fetch failed: {e}",
                manual_instructions=self.MANUAL_DOWNLOAD_INSTRUCTIONS,
            )

    def _fetch_from_fred(self) -> pd.DataFrame:
        """Fetch crude oil price series from FRED (no API key needed for CSV)."""
        url = f"{_FRED_BASE_URL}?id={self._fred_series}"
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            raise Exception(f"FRED returned HTTP {resp.status_code}")
        df = pd.read_csv(io.StringIO(resp.text))
        if df.empty:
            raise Exception("FRED returned empty CSV.")
        return df

    def validate(self, raw_path: Path) -> List[str]:
        errors = self._require_non_empty(raw_path)
        if errors:
            return errors

        try:
            df = pd.read_csv(raw_path, nrows=10)
        except Exception as e:
            return [f"Cannot read CSV: {e}"]

        if len(df.columns) < 2:
            errors.append(f"Expected at least 2 columns (date + price). Got: {list(df.columns)}")

        # FRED format: DATE, <SERIES_ID>
        # Check for date column
        date_col = df.columns[0]
        try:
            pd.to_datetime(df[date_col].head(5))
        except Exception:
            errors.append(f"First column '{date_col}' does not appear to be dates.")

        return errors

    def load_normalized(self) -> pd.DataFrame:
        """Load and normalise crude oil CSV.

        Returns DataFrame with columns:
          date, price_usd, benchmark, source, source_is_indian
        """
        raw_path = self.raw_output_dir / self._filename
        if not raw_path.exists():
            raise FileNotFoundError(
                f"Crude oil file not found: {raw_path}\n"
                f"{self.MANUAL_DOWNLOAD_INSTRUCTIONS}"
            )

        df = pd.read_csv(raw_path)
        df.columns = [c.strip() for c in df.columns]

        # FRED format: DATE | <SERIES_ID> (e.g. DCOILBRENTEU)
        date_col = df.columns[0]
        price_col = df.columns[1]

        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col])

        # FRED uses "." for missing values
        price = pd.to_numeric(df[price_col].replace(".", None), errors="coerce")

        result = pd.DataFrame({
            "date": df[date_col],
            "price_usd": price,
            "benchmark": self._benchmark,
            "source": f"FRED_{self._fred_series}",
            "source_is_indian": False,  # Explicitly documented
            "notes": "Exogenous context. Non-Indian source. Intentional.",
        })

        result = result.sort_values("date").reset_index(drop=True)
        return result
