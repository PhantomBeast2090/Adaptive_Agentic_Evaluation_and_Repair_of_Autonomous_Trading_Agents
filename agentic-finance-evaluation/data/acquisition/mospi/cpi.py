"""MoSPI CPI (Consumer Price Index) Acquisition Adapter.

PRIMARY SOURCE: Ministry of Statistics and Programme Implementation (MoSPI)
  CPI Data: https://mospi.gov.in/consumer-price-indices-cpi

CPI SERIES AVAILABLE:
  - CPI Combined (Urban + Rural) — primary series
  - CPI Urban
  - CPI Rural
  - Sub-indices: Food, Core (CPI ex-food & fuel), etc.

CRITICAL — INFORMATION AVAILABILITY:
  CPI for month M is released approximately 5-6 weeks after month-end.
  Example: CPI for January 2024 is released approximately in mid-February 2024.

  Therefore:
    observation_date = last day of the reference month (e.g. 2024-01-31)
    availability_date = actual release date (e.g. approximately 2024-02-15)

  The agent MUST NOT receive January CPI data before mid-February.
  Using observation_date as availability_date would constitute leakage.

MANUAL DOWNLOAD INSTRUCTIONS:
  1. Visit: https://mospi.gov.in/consumer-price-indices-cpi
  2. Download the historical CPI data table (usually Excel/CSV)
  3. Also available from: https://data.gov.in (search "Consumer Price Index")
  4. Place at: data/raw/india/macro/cpi_combined.csv

  For release dates (availability_date):
  - MoSPI publishes press releases on the day of release
  - Check: https://mospi.gov.in/press-release-consumer-price-index
  - Or RBI calendar: https://www.rbi.org.in/scripts/Bs_PressReleaseDisplay.aspx
  - Release dates are typically the 12th-14th of the month following
  - Place release date mapping at: data/raw/india/macro/cpi_release_dates.csv

EXPECTED COLUMNS (CPI data):
  Month/Year | CPI_Combined | CPI_Urban | CPI_Rural | [sub-indices]

EXPECTED COLUMNS (release dates):
  reference_month | release_date

EXPECTED COVERAGE (MoSPI):
  New CPI series (base 2012=100): from January 2012
  Old CPI series (various bases): from earlier periods
  Note: "expected" ≠ "verified" — coverage audit determines actual coverage.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import pandas as pd

from data.acquisition.base import AcquisitionError, BaseAdapter
from src.schemas.india_data import (
    DataFrequency,
    DataTier,
)


class MoSPICPIAdapter(BaseAdapter):
    """Acquire MoSPI Consumer Price Index data with release dates."""

    MANUAL_DOWNLOAD_INSTRUCTIONS = """
MoSPI CPI Manual Download:
1. Visit: https://mospi.gov.in/consumer-price-indices-cpi
2. Download the "CPI Data" historical table (Excel or CSV)
3. Place at: data/raw/india/macro/cpi_combined.csv

For release dates (CRITICAL for information availability):
1. Visit: https://mospi.gov.in/press-release-consumer-price-index
2. Extract the date each month's CPI was released
3. Or use: https://www.rbi.org.in/scripts/Bs_PressReleaseDisplay.aspx
   (filter by CPI press releases)
4. Create a CSV with columns: reference_month, release_date
   reference_month format: YYYY-MM (e.g. 2024-01 for January 2024)
   release_date format: YYYY-MM-DD
5. Place at: data/raw/india/macro/cpi_release_dates.csv

Alternative automated source (secondary):
  RBI DBIE also carries CPI data:
  https://dbie.rbi.org.in/ → Price and Monetary → Consumer Price Index
  HOWEVER: DBIE may not include individual release dates.
  Use MoSPI as the primary source.

Expected CPI CSV structure:
  Month/Year | CPI_Combined (General) | CPI_Urban | CPI_Rural | ...
  OR: Month | Year | CPI | [sub-indices]
  Base year: 2012=100 for the new series
"""

    @property
    def dataset_id(self) -> str:
        return "mospi_cpi_combined_monthly"

    @property
    def tier(self) -> DataTier:
        return DataTier.C

    @property
    def asset_class(self) -> str:
        return "macro"

    @property
    def variable(self) -> str:
        return "CPI_COMBINED_MONTHLY"

    @property
    def source_institution(self) -> str:
        return "MOSPI"

    @property
    def frequency(self) -> DataFrequency:
        return DataFrequency.MONTHLY

    @property
    def raw_output_dir(self) -> Path:
        return self.base_dir / "data" / "raw" / "india" / "macro"

    def acquire(self) -> Path:
        output_path = self.raw_output_dir / "cpi_combined.csv"

        if output_path.exists() and output_path.stat().st_size > 200:
            self.logger.info(f"CPI file already present: {output_path}")
            return output_path

        raise AcquisitionError(
            dataset_id=self.dataset_id,
            source="MoSPI CPI / mospi.gov.in",
            reason=(
                "MoSPI CPI data requires web download from mospi.gov.in. "
                "Automated download is not reliably possible. "
                "Release dates (critical for information availability) "
                "require separate collection from press release archives."
            ),
            manual_instructions=self.MANUAL_DOWNLOAD_INSTRUCTIONS,
        )

    def validate(self, raw_path: Path) -> List[str]:
        errors = self._require_non_empty(raw_path)
        if errors:
            return errors

        try:
            df = pd.read_csv(raw_path, nrows=5)
        except Exception as e:
            return [f"Cannot read CSV: {e}"]

        # Should have a date/month column and a CPI column
        date_found = any(
            any(k in c.lower() for k in ["month", "year", "date", "period"])
            for c in df.columns
        )
        cpi_found = any(
            any(k in c.lower() for k in ["cpi", "index", "price", "general"])
            for c in df.columns
        )
        if not date_found:
            errors.append(f"No date/month column found. Columns: {list(df.columns)}")
        if not cpi_found:
            errors.append(f"No CPI value column found. Columns: {list(df.columns)}")

        return errors

    def load_normalized(self, allow_estimated_availability: bool = False) -> pd.DataFrame:
        """Load and normalise CPI CSV with release dates.

        Returns DataFrame with columns:
          observation_date, availability_date, variable, value, unit,
          revision_version, frequency, source

        CRITICAL: availability_date comes from the release_dates CSV.
        If release_dates CSV is missing, an estimated lag of 45 days is
        applied and this is CLEARLY flagged in notes.
        """
        raw_path = self.raw_output_dir / "cpi_combined.csv"
        release_path = self.raw_output_dir / "cpi_release_dates.csv"

        if not raw_path.exists():
            raise FileNotFoundError(
                f"CPI file not found: {raw_path}\n"
                f"{self.MANUAL_DOWNLOAD_INSTRUCTIONS}"
            )

        df = pd.read_csv(raw_path)
        df.columns = [c.strip() for c in df.columns]

        # Detect date column (Month/Year or combined)
        date_col = next(
            (c for c in df.columns
             if any(k in c.lower() for k in ["month", "period", "date"])),
            df.columns[0],
        )

        # Detect CPI value column (General / Combined)
        cpi_col = next(
            (c for c in df.columns
             if any(k in c.lower() for k in
                    ["general", "combined", "all india", "cpi", "index"])),
            df.columns[1] if len(df.columns) > 1 else None,
        )

        # Parse dates
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col])

        # observation_date = last day of the reference month
        obs_dates = df[date_col].dt.to_period("M").dt.to_timestamp("M")

        # Load release dates if available
        use_estimated_lag = False
        if release_path.exists():
            rdf = pd.read_csv(release_path)
            rdf.columns = [c.strip() for c in rdf.columns]
            rdf["reference_month"] = pd.to_datetime(
                rdf.get("reference_month", rdf.columns[0]), errors="coerce"
            )
            rdf["release_date"] = pd.to_datetime(
                rdf.get("release_date", rdf.columns[1]), dayfirst=True, errors="coerce"
            )
            # Merge to get actual release dates
            obs_period = obs_dates.dt.to_period("M")
            rel_period = rdf["reference_month"].dt.to_period("M")
            mapping = dict(zip(rel_period, rdf["release_date"]))
            avail_dates = obs_period.map(mapping)
        else:
            if not allow_estimated_availability:
                raise ValueError(
                    "Actual CPI release dates are required for point-in-time use. "
                    "Provide data/raw/india/macro/cpi_release_dates.csv; "
                    "estimated lags cannot become agent-facing data."
                )
            use_estimated_lag = True
            avail_dates = obs_dates + pd.Timedelta(days=45)
            self.logger.warning(
                "Using estimated CPI availability dates in explicitly restricted mode."
            )

        result = pd.DataFrame({
            "observation_date": obs_dates,
            "availability_date": avail_dates,
            "variable": "CPI_COMBINED",
            "value": (
                pd.to_numeric(df[cpi_col], errors="coerce") if cpi_col else None
            ),
            "unit": "index_2012eq100",
            "revision_version": 0,
            "frequency": "monthly",
            "source": "MOSPI",
            "availability_date_estimated": use_estimated_lag,
        })

        result = result.sort_values("observation_date").reset_index(drop=True)
        return result
