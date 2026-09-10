"""MoSPI IIP (Index of Industrial Production) Acquisition Adapter.

PRIMARY SOURCE: Ministry of Statistics and Programme Implementation (MoSPI)
  IIP Data: https://mospi.gov.in/index-industrial-production

CRITICAL — INFORMATION AVAILABILITY (same as CPI):
  IIP for month M is released approximately 6 weeks after month-end.
  Example: IIP for January 2024 is released approximately 11th February 2024.

  observation_date = last day of the reference month (e.g. 2024-01-31)
  availability_date = actual release date (approximately 6 weeks after)

  The agent MUST NOT receive January IIP before mid-February.

REVISION STRUCTURE:
  IIP data is subject to revision:
  - First release (Advance): approximately 6 weeks after month end
  - Revised data: in the subsequent month's release
  The revision_version field tracks this.

MANUAL DOWNLOAD INSTRUCTIONS:
  1. Visit: https://mospi.gov.in/index-industrial-production
  2. Download the IIP historical data (Excel/CSV)
  3. Place at: data/raw/india/macro/iip_general.csv

  For release dates:
  1. Visit MoSPI press releases for IIP
  2. Record: reference_month | release_date
  3. Place at: data/raw/india/macro/iip_release_dates.csv

EXPECTED COLUMNS:
  Month/Year | IIP_General | IIP_Manufacturing | IIP_Mining | IIP_Electricity

EXPECTED COVERAGE:
  IIP data available from approximately 2004 (base year 2011-12=100).
  Earlier data with older base years exists but needs base-year harmonisation.
  Note: "expected" ≠ "verified" — coverage audit determines actual coverage.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd

from data.acquisition.base import AcquisitionError, BaseAdapter
from src.schemas.india_data import (
    DataFrequency,
    DataTier,
)


class MoSPIIIPAdapter(BaseAdapter):
    """Acquire MoSPI IIP data with release dates."""

    MANUAL_DOWNLOAD_INSTRUCTIONS = """
MoSPI IIP Manual Download:
1. Visit: https://mospi.gov.in/index-industrial-production
2. Download historical IIP data (Excel or CSV)
3. Place at: data/raw/india/macro/iip_general.csv

For release dates (CRITICAL for information availability):
1. Visit MoSPI press releases or IIP release calendar
2. Record the date each month's IIP was first released
3. Create: data/raw/india/macro/iip_release_dates.csv
   Columns: reference_month (YYYY-MM), release_date (YYYY-MM-DD)

Alternative source:
  RBI DBIE: https://dbie.rbi.org.in/
  Navigate: Real Economy → Industry → IIP

Expected IIP CSV structure:
  Month/Year | General | Mining | Manufacturing | Electricity
  Base year: 2011-12=100 (current series)
"""

    @property
    def dataset_id(self) -> str:
        return "mospi_iip_general_monthly"

    @property
    def tier(self) -> DataTier:
        return DataTier.C

    @property
    def asset_class(self) -> str:
        return "macro"

    @property
    def variable(self) -> str:
        return "IIP_GENERAL_MONTHLY"

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
        output_path = self.raw_output_dir / "iip_general.csv"

        if output_path.exists() and output_path.stat().st_size > 200:
            self.logger.info(f"IIP file already present: {output_path}")
            return output_path

        raise AcquisitionError(
            dataset_id=self.dataset_id,
            source="MoSPI IIP / mospi.gov.in",
            reason=(
                "MoSPI IIP data requires web download. "
                "Release dates (critical for information availability) "
                "require separate collection."
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

        date_found = any(
            any(k in c.lower() for k in ["month", "year", "date"])
            for c in df.columns
        )
        iip_found = any(
            any(k in c.lower() for k in ["general", "iip", "index", "manufacture"])
            for c in df.columns
        )
        if not date_found:
            errors.append(f"No date/month column found. Columns: {list(df.columns)}")
        if not iip_found:
            errors.append(f"No IIP value column. Columns: {list(df.columns)}")

        return errors

    def load_normalized(self) -> pd.DataFrame:
        """Load and normalise IIP CSV with release dates.

        Same availability_date logic as CPI adapter.
        """
        raw_path = self.raw_output_dir / "iip_general.csv"
        release_path = self.raw_output_dir / "iip_release_dates.csv"

        if not raw_path.exists():
            raise FileNotFoundError(
                f"IIP file not found: {raw_path}\n"
                f"{self.MANUAL_DOWNLOAD_INSTRUCTIONS}"
            )

        df = pd.read_csv(raw_path)
        df.columns = [c.strip() for c in df.columns]

        date_col = next(
            (c for c in df.columns
             if any(k in c.lower() for k in ["month", "period", "date"])),
            df.columns[0],
        )

        iip_col = next(
            (c for c in df.columns
             if any(k in c.lower() for k in ["general", "all", "iip"])),
            df.columns[1] if len(df.columns) > 1 else None,
        )

        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col])
        obs_dates = df[date_col].dt.to_period("M").dt.to_timestamp("M")

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
            mapping = dict(zip(
                rdf["reference_month"].dt.to_period("M"),
                rdf["release_date"]
            ))
            avail_dates = obs_dates.dt.to_period("M").map(mapping)
        else:
            use_estimated_lag = True
            avail_dates = obs_dates + pd.Timedelta(days=42)  # ~6 weeks
            self.logger.warning(
                "IIP release dates CSV not found. Using estimated 42-day lag. "
                "Provide data/raw/india/macro/iip_release_dates.csv for accuracy."
            )

        result = pd.DataFrame({
            "observation_date": obs_dates,
            "availability_date": avail_dates,
            "variable": "IIP_GENERAL",
            "value": (
                pd.to_numeric(df[iip_col], errors="coerce") if iip_col else None
            ),
            "unit": "index_2011_12eq100",
            "revision_version": 0,
            "frequency": "monthly",
            "source": "MOSPI",
            "availability_date_estimated": use_estimated_lag,
        })

        result = result.sort_values("observation_date").reset_index(drop=True)
        return result
