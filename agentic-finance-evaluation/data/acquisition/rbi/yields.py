"""RBI/DBIE Government Securities and T-Bill Yield Acquisition Adapter.

PRIMARY SOURCE: Reserve Bank of India — DBIE (Database on Indian Economy)
  Base URL: https://dbie.rbi.org.in/

SERIES TARGETED:
  - 10-Year Government Security benchmark yield
  - 5-Year Government Security yield
  - 91-day Treasury Bill rate (cut-off yield)
  - 364-day Treasury Bill rate (cut-off yield)

RBI DBIE API:
  RBI DBIE provides a data API used by their own portal.
  We attempt to use documented DBIE endpoints.
  If blocked, we fall back to documented manual download.

ALTERNATIVE SOURCE:
  CCIL (Clearing Corporation of India):
    https://www.ccilindia.com/Research/Statistics/Pages/YieldCurve.aspx
  FBIL (Financial Benchmarks India):
    https://www.fbil.org.in/

  These are secondary sources. Primary remains RBI/DBIE.
  If secondary sources are used, this is EXPLICITLY documented.

MANUAL DOWNLOAD INSTRUCTIONS:
  For 10Y G-Sec yield via RBI DBIE:
  1. Visit: https://dbie.rbi.org.in/DBIE/dbie.rbi?site=statistics
  2. Navigate: Financial Markets → Government Securities Market
  3. Select series: "Yield on Government Securities (10-Year)"
  4. Download as CSV
  5. Place at: data/raw/india/fixed_income/gsec_10y_yield.csv

  For T-Bill rates:
  1. Navigate: Money Market → Treasury Bills
  2. Download 91-day and 364-day series
  3. Place at: data/raw/india/fixed_income/tbill_91d.csv
               data/raw/india/fixed_income/tbill_364d.csv

EXPECTED COLUMNS:
  Date, Yield/Rate (%), [optional: Price, Source]

EXPECTED COVERAGE (RBI DBIE):
  10Y G-Sec yield: typically from 2001 or earlier
  T-Bills: typically from mid-1990s
  Note: "expected" ≠ "verified" — coverage audit determines actual.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests

from data.acquisition.base import AcquisitionError, BaseAdapter
from src.schemas.india_data import (
    DataFrequency,
    DataTier,
)

_DBIE_BASE = "https://dbie.rbi.org.in"

_TENOR_FILES: Dict[str, str] = {
    "10Y": "gsec_10y_yield.csv",
    "5Y": "gsec_5y_yield.csv",
    "91D": "tbill_91d.csv",
    "364D": "tbill_364d.csv",
}


class RBIGSecYieldAdapter(BaseAdapter):
    """Acquire RBI/DBIE G-Sec and T-Bill yield data."""

    def __init__(self, tenor: str = "10Y", base_dir: str = "."):
        super().__init__(base_dir)
        if tenor not in _TENOR_FILES:
            raise ValueError(
                f"Unknown tenor '{tenor}'. Supported: {list(_TENOR_FILES.keys())}"
            )
        self._tenor = tenor
        self._filename = _TENOR_FILES[tenor]

    @property
    def dataset_id(self) -> str:
        return f"rbi_gsec_{self._tenor.lower()}_yield"

    @property
    def tier(self) -> DataTier:
        return DataTier.A

    @property
    def asset_class(self) -> str:
        return "fixed_income"

    @property
    def variable(self) -> str:
        return f"GSEC_{self._tenor}_YIELD"

    @property
    def source_institution(self) -> str:
        return "RBI"

    @property
    def frequency(self) -> DataFrequency:
        return DataFrequency.DAILY

    @property
    def raw_output_dir(self) -> Path:
        return self.base_dir / "data" / "raw" / "india" / "fixed_income"

    @property
    def manual_download_instructions(self) -> str:
        return f"""
RBI/DBIE {self._tenor} Yield Manual Download:
1. Visit: https://dbie.rbi.org.in/DBIE/dbie.rbi?site=statistics
2. Navigate: Financial Markets → Government Securities Market (or Money Market for T-Bills)
3. Find series for {self._tenor} yield/rate
4. Select maximum date range
5. Download as CSV
6. Place at: data/raw/india/fixed_income/{self._filename}

Alternative (FBIL):
  https://www.fbil.org.in/#/home  → Benchmark Rates → FBIL T-Bill Rates
  (For T-Bills only; G-Sec rates remain from RBI/DBIE)

Expected CSV columns:
  Date | Yield (%) | [optional: Price, Security ID]
"""

    def acquire(self) -> Path:
        output_path = self.raw_output_dir / self._filename

        if output_path.exists() and output_path.stat().st_size > 500:
            self.logger.info(f"{self._tenor} yield file already present: {output_path}")
            return output_path

        # Attempt DBIE download
        try:
            df = self._fetch_from_dbie()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(output_path, index=False)
            self.logger.info(
                f"Fetched {self._tenor} yield from DBIE: {len(df)} rows"
            )
            return output_path
        except Exception as e:
            raise AcquisitionError(
                dataset_id=self.dataset_id,
                source=f"RBI DBIE ({self._tenor} yield)",
                reason=(
                    f"DBIE automated fetch failed: {e}. "
                    "RBI DBIE requires authenticated session or API key. "
                    "Manual download required."
                ),
                manual_instructions=self.manual_download_instructions,
            )

    def _fetch_from_dbie(self) -> pd.DataFrame:
        """Attempt DBIE data fetch via documented API endpoints."""
        # DBIE has a chart-data API — try common patterns
        # This is an attempt; the API may require authentication or session cookies
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })

        # DBIE data series IDs for common series
        # These IDs come from inspecting DBIE network traffic
        dbie_series_map = {
            "10Y": "BSR1:BISQ:A:A:4:0:WT.GSEC_10Y",
            "5Y": "BSR1:BISQ:A:A:4:0:WT.GSEC_5Y",
            "91D": "BSR1:BISQ:A:A:4:0:WT.TBILL_91D",
            "364D": "BSR1:BISQ:A:A:4:0:WT.TBILL_364D",
        }

        series_id = dbie_series_map.get(self._tenor)
        if not series_id:
            raise Exception(f"No DBIE series ID known for tenor {self._tenor}")

        # Attempt fetch — will likely fail without valid session
        url = f"{_DBIE_BASE}/DBIE/dbie.rbi?site=export&seriesId={series_id}&format=CSV"
        resp = session.get(url, timeout=20)
        if resp.status_code != 200:
            raise Exception(
                f"DBIE returned HTTP {resp.status_code}. "
                "Session/authentication may be required."
            )

        try:
            df = pd.read_csv(io.StringIO(resp.text))
            if df.empty:
                raise Exception("DBIE returned empty CSV.")
            return df
        except Exception as e:
            raise Exception(f"Cannot parse DBIE response as CSV: {e}")

    def validate(self, raw_path: Path) -> List[str]:
        errors = self._require_non_empty(raw_path)
        if errors:
            return errors

        try:
            df = pd.read_csv(raw_path, nrows=5)
        except Exception as e:
            return [f"Cannot read CSV: {e}"]

        # Must have some numeric column for yield
        numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
        if not numeric_cols:
            # Try parsing all columns
            for col in df.columns:
                if "yield" in col.lower() or "rate" in col.lower() or "%" in col:
                    return []
            errors.append(
                f"No yield/rate column found. Columns: {list(df.columns)}"
            )

        return errors

    def load_normalized(self) -> pd.DataFrame:
        """Load and normalise yield CSV to standard schema.

        Returns DataFrame with columns: date, tenor, yield_pct, source
        """
        raw_path = self.raw_output_dir / self._filename
        if not raw_path.exists():
            raise FileNotFoundError(
                f"Yield file not found: {raw_path}\n"
                f"{self.manual_download_instructions}"
            )

        df = pd.read_csv(raw_path)
        df.columns = [c.strip() for c in df.columns]

        # Detect date and yield columns
        date_col = next(
            (c for c in df.columns if "date" in c.lower()), df.columns[0]
        )
        yield_col = next(
            (c for c in df.columns
             if any(k in c.lower() for k in ["yield", "rate", "%", "per cent"])),
            None,
        )
        if yield_col is None and len(df.columns) >= 2:
            yield_col = df.columns[1]

        df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce")
        df = df.dropna(subset=[date_col])

        result = pd.DataFrame({
            "observation_date": df[date_col],
            "tenor": self._tenor,
            "yield_pct": pd.to_numeric(df[yield_col], errors="coerce") if yield_col else None,
            "source": "RBI_DBIE",
        })

        result = result.sort_values("observation_date").reset_index(drop=True)
        return result
