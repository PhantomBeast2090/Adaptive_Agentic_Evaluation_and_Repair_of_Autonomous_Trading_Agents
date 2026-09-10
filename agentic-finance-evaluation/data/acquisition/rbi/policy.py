"""RBI Monetary Policy Rate (Repo Rate) Acquisition Adapter.

PRIMARY SOURCE: Reserve Bank of India — Monetary Policy
  Policy decisions: https://www.rbi.org.in/scripts/BS_PressReleaseDisplay.aspx
  Historical rates: https://dbie.rbi.org.in/

CRITICAL DISTINCTION — observation_date vs availability_date:
  For repo rate:
  - availability_date = announcement date (when MPC decision is published)
  - observation_date = effective date (when the rate takes effect)
  These are often the same day but MUST be tracked separately.
  The agent MUST NOT know a rate change before the announcement date.

EVENT-BASED SERIES:
  The repo rate is an event-based state variable, NOT a daily time series.
  Between MPC meetings, the rate remains constant.
  The processed layer will create a daily state series by forward-filling
  from each announcement date. This is documented and intentional.

MANUAL DOWNLOAD INSTRUCTIONS:
  1. Visit: https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx
     → Filter by "Monetary Policy" for MPC decision press releases
  2. Or use RBI DBIE:
     https://dbie.rbi.org.in/ → Financial Sector → Monetary Policy
     → Key Policy Rates (Repo Rate, Reverse Repo, etc.)
  3. Download as CSV
  4. Place at: data/raw/india/macro/rbi_policy_rate.csv

EXPECTED COLUMNS:
  Date | Rate_Type | Rate_% | [Announcement_Date | Effective_Date | Stance]

EXPECTED COVERAGE:
  RBI repo rate history: approximately from 2001 (LAF era).
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


class RBIPolicyRateAdapter(BaseAdapter):
    """Acquire RBI Monetary Policy (Repo Rate) historical data."""

    MANUAL_DOWNLOAD_INSTRUCTIONS = """
RBI Policy Rate Manual Download:

Option A — RBI DBIE (preferred):
  1. Visit: https://dbie.rbi.org.in/
  2. Navigate: Financial Sector → Monetary Policy → Key Policy Rates
  3. Select: Repo Rate (and optionally: Reverse Repo, MSF Rate, CRR, SLR)
  4. Download as CSV
  5. Place at: data/raw/india/macro/rbi_policy_rate.csv

Option B — RBI Handbook of Statistics:
  1. Visit: https://www.rbi.org.in/Scripts/AnnualPublications.aspx?head=Handbook+of+Statistics+on+Indian+Economy
  2. Find the monetary policy table
  3. Download relevant tables

CRITICAL: Each record must include:
  - effective_date (when rate took effect)
  - announcement_date (when RBI published the decision)
  - rate_type (e.g. REPO, REVERSE_REPO, MSF)
  - rate_pct (rate in percentage, e.g. 6.5)
  - [optional] stance (accommodative, neutral, withdrawal of accommodation)

If the source only provides effective dates, record both effective_date and
announcement_date as the same value and flag in notes that announcement dates
were not separately captured.
"""

    @property
    def dataset_id(self) -> str:
        return "rbi_policy_rate_events"

    @property
    def tier(self) -> DataTier:
        return DataTier.C  # Exogenous macro context

    @property
    def asset_class(self) -> str:
        return "policy"

    @property
    def variable(self) -> str:
        return "RBI_REPO_RATE"

    @property
    def source_institution(self) -> str:
        return "RBI"

    @property
    def frequency(self) -> DataFrequency:
        return DataFrequency.EVENT_BASED

    @property
    def raw_output_dir(self) -> Path:
        return self.base_dir / "data" / "raw" / "india" / "macro"

    def acquire(self) -> Path:
        output_path = self.raw_output_dir / "rbi_policy_rate.csv"

        if output_path.exists() and output_path.stat().st_size > 200:
            self.logger.info(f"Policy rate file already present: {output_path}")
            return output_path

        raise AcquisitionError(
            dataset_id=self.dataset_id,
            source="RBI DBIE / RBI website",
            reason=(
                "RBI policy rate data requires web navigation through DBIE. "
                "Manual download is required to ensure accurate announcement dates "
                "are captured (not just effective dates)."
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

        # Need at least a date and rate column
        date_found = any("date" in c.lower() for c in df.columns)
        rate_found = any(
            any(k in c.lower() for k in ["rate", "repo", "percent", "%"])
            for c in df.columns
        )
        if not date_found:
            errors.append(f"No date column. Columns: {list(df.columns)}")
        if not rate_found:
            errors.append(f"No rate column. Columns: {list(df.columns)}")

        return errors

    def load_normalized(self) -> pd.DataFrame:
        """Load and normalise policy rate CSV.

        Returns DataFrame with columns:
          observation_date, availability_date, rate_type, rate_pct, source
        """
        raw_path = self.raw_output_dir / "rbi_policy_rate.csv"
        if not raw_path.exists():
            raise FileNotFoundError(
                f"Policy rate file not found: {raw_path}\n"
                f"{self.MANUAL_DOWNLOAD_INSTRUCTIONS}"
            )

        df = pd.read_csv(raw_path)
        df.columns = [c.strip() for c in df.columns]

        # Try to find observation/effective date
        obs_col = next(
            (c for c in df.columns
             if any(k in c.lower() for k in
                    ["effective", "observation", "from", "date"])),
            df.columns[0],
        )

        # Try to find announcement/availability date
        avail_col = next(
            (c for c in df.columns
             if any(k in c.lower() for k in
                    ["announcement", "publish", "release", "decision"])),
            None,
        )

        rate_col = next(
            (c for c in df.columns
             if any(k in c.lower() for k in ["rate", "repo", "%", "percent"])),
            None,
        )

        df[obs_col] = pd.to_datetime(df[obs_col], dayfirst=True, errors="coerce")
        df = df.dropna(subset=[obs_col])

        result = pd.DataFrame({
            "observation_date": df[obs_col],
            "availability_date": (
                pd.to_datetime(df[avail_col], dayfirst=True, errors="coerce")
                if avail_col else df[obs_col]
            ),
            "rate_type": (
                df["rate_type"] if "rate_type" in df.columns else "REPO"
            ),
            "rate_pct": (
                pd.to_numeric(df[rate_col], errors="coerce") if rate_col else None
            ),
            "source": "RBI",
        })

        # Warn if availability_date == observation_date (announcement dates not captured)
        if avail_col is None:
            self.logger.warning(
                "No announcement date column found. Using effective_date as "
                "availability_date. This may not accurately represent when "
                "the rate change was announced."
            )

        result = result.sort_values("observation_date").reset_index(drop=True)
        return result

    def build_daily_series(self, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        """Build a daily forward-filled policy rate series.

        The forward-fill is applied from availability_date (NOT observation_date).
        This ensures the daily series reflects what was publicly known each day.

        Returns a DataFrame indexed by date with columns:
          rate_pct, rate_type, availability_date, source
        """
        events = self.load_normalized()
        events["availability_date"] = pd.to_datetime(events["availability_date"])

        # Create a full calendar date range
        date_range = pd.date_range(start=start, end=end, freq="D")
        daily = pd.DataFrame(index=date_range)
        daily.index.name = "date"

        # For each date, find the most recent announced rate
        for idx in daily.index:
            known = events[events["availability_date"] <= idx]
            if not known.empty:
                latest = known.iloc[-1]
                daily.loc[idx, "rate_pct"] = latest["rate_pct"]
                daily.loc[idx, "rate_type"] = latest["rate_type"]
                daily.loc[idx, "availability_date"] = str(latest["availability_date"])

        daily["source"] = "RBI"
        return daily
