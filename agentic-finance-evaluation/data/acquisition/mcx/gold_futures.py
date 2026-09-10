"""MCX Gold Futures Acquisition Adapter.

PRIMARY SOURCE: Multi Commodity Exchange of India (MCX)
  Historical data: https://www.mcxindia.com/market-data/historical-data

CRITICAL DESIGN DECISIONS:
  1. Individual contracts are preserved — NO silent roll concatenation.
  2. The roll methodology must be explicit and separately documented.
  3. Look-ahead through future contract knowledge is prohibited.

MCX GOLD CONTRACTS:
  - GOLD (1 kg, main contract)
  - GOLDM (10g, mini contract — more liquid for some periods)
  - GOLDPETAL (1g, micro contract)
  Primary research focus: GOLD (1 kg) and GOLDM (10g) contracts.

CONTRACT NAMING CONVENTION:
  MCX gold contracts are named by month/year:
    GOLDJAN2024, GOLDFEB2024, etc.
  Each contract trades approximately 60 days before expiry.
  Delivery months: February, April, June, August, October, December

ROLL METHODOLOGY (NOT APPLIED HERE — documented for later):
  Common approaches:
    1. Front-month roll: switch to next contract N days before expiry
    2. Open-interest weighted roll
    3. Panama method (price-level adjustment)
  The chosen methodology must be decided AFTER coverage audit.
  No synthetic continuous series is constructed in this module.

MANUAL DOWNLOAD INSTRUCTIONS:
  1. Visit: https://www.mcxindia.com/market-data/historical-data
  2. Select: Commodity = Gold (or Gold Mini)
  3. For each contract month/year, download historical data
  4. Place individual CSV files at:
     data/raw/india/gold/mcx_gold_<contractID>.csv
     e.g.: data/raw/india/gold/mcx_gold_GOLDJAN2024.csv

  Alternative: MCX bulk download (if available via paid subscription):
    Contact MCX data services for bulk historical downloads

EXPECTED COLUMNS (MCX historical data CSV):
  Date | Open | High | Low | Close | Volume | Open Interest | Value (Lakhs)

EXPECTED COVERAGE:
  MCX Gold futures: approximately from November 2003 (MCX launch).
  Note: "expected" ≠ "verified" — coverage audit determines actual coverage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from data.acquisition.base import AcquisitionError, BaseAdapter
from src.schemas.india_data import (
    DataFrequency,
    DataTier,
)

MCX_GOLD_STANDARD_COLS = {
    "Date": "trade_date",
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume",
    "Open Interest": "open_interest",
    "Value": "turnover",
    "Expiry Date": "expiry_date",
}


class MCXGoldFuturesAdapter(BaseAdapter):
    """Acquire MCX Gold Futures data (individual contracts).

    Each individual contract file is loaded separately.
    NO continuous series is constructed here.
    """

    MANUAL_DOWNLOAD_INSTRUCTIONS = """
MCX Gold Futures Manual Download Instructions:

For EACH contract month:
1. Visit: https://www.mcxindia.com/market-data/historical-data
2. Select: Commodity = GOLD (or GOLDM for mini)
3. In the contract dropdown, select a specific month/year
4. Set date range = contract full trading period
5. Click "Get Data" → Download as CSV
6. Name the file: mcx_gold_<CONTRACTSYMBOL>.csv
   Example: mcx_gold_GOLDFEB2024.csv
7. Place at: data/raw/india/gold/

Repeat for all contracts in the desired history window.

For bulk historical data (alternative):
  MCX data vendor services may provide bulk downloads.
  Quantsapp, Traders Carnival, NSE Data Analytics may have MCX data.
  If using a secondary source, document it in the manifest.

Expected CSV columns per file:
  Date | Open | High | Low | Close | Volume | Open Interest | Value (Lakhs)
  [optional: Expiry Date | Contract Symbol]

IMPORTANT: Each file = one contract. Do NOT manually concatenate contracts.
The roll methodology will be designed separately after coverage audit.
"""

    @property
    def dataset_id(self) -> str:
        return "mcx_gold_futures_individual_contracts"

    @property
    def tier(self) -> DataTier:
        return DataTier.A

    @property
    def asset_class(self) -> str:
        return "gold"

    @property
    def variable(self) -> str:
        return "MCX_GOLD_FUTURES_DAILY"

    @property
    def source_institution(self) -> str:
        return "MCX"

    @property
    def frequency(self) -> DataFrequency:
        return DataFrequency.DAILY

    @property
    def raw_output_dir(self) -> Path:
        return self.base_dir / "data" / "raw" / "india" / "gold"

    def acquire(self) -> Path:
        """Check for existing gold futures files."""
        existing = list(self.raw_output_dir.glob("mcx_gold_*.csv"))
        if existing:
            self.logger.info(
                f"Found {len(existing)} MCX gold contract files in {self.raw_output_dir}"
            )
            index_path = self.raw_output_dir / "mcx_gold_contract_index.txt"
            with open(index_path, "w") as f:
                f.write(f"MCX gold contract files found: {len(existing)}\n")
                for p in sorted(existing):
                    f.write(f"{p.name}\n")
            return index_path

        raise AcquisitionError(
            dataset_id=self.dataset_id,
            source="MCX Historical Data",
            reason=(
                "No MCX gold futures CSV files found in data/raw/india/gold/. "
                "MCX requires individual contract downloads per month/year via "
                "their website. Automated bulk download is not available without "
                "a data vendor subscription."
            ),
            manual_instructions=self.MANUAL_DOWNLOAD_INSTRUCTIONS,
        )

    def validate(self, raw_path: Path) -> List[str]:
        errors = self._require_non_empty(raw_path)
        if errors:
            return errors

        csvs = list(self.raw_output_dir.glob("mcx_gold_*.csv"))
        if not csvs:
            errors.append("No mcx_gold_*.csv files found.")
            return errors

        # Validate a sample file
        sample = csvs[0]
        try:
            df = pd.read_csv(sample, nrows=3)
            required = {"Close"}
            missing = required - {c.strip() for c in df.columns}
            if missing:
                errors.append(f"Missing columns in {sample.name}: {missing}")
        except Exception as e:
            errors.append(f"Cannot read {sample.name}: {e}")

        return errors

    def load_normalized(
        self,
        contract_filter: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Load all MCX gold contract files and return combined DataFrame.

        Each row preserves the individual contract identity.
        NO roll concatenation is applied.

        Args:
            contract_filter: If provided, only load these contract symbols.

        Returns:
            DataFrame with columns:
              trade_date, contract_symbol, expiry_date, open, high, low,
              close, settlement_price, open_interest, volume, turnover, source
        """
        csv_files = sorted(self.raw_output_dir.glob("mcx_gold_*.csv"))
        if not csv_files:
            raise FileNotFoundError(
                f"No MCX gold CSV files in {self.raw_output_dir}\n"
                f"{self.MANUAL_DOWNLOAD_INSTRUCTIONS}"
            )

        frames = []
        for f in csv_files:
            # Extract contract symbol from filename
            contract_symbol = f.stem.replace("mcx_gold_", "").upper()

            if contract_filter and contract_symbol not in contract_filter:
                continue

            try:
                df = pd.read_csv(f)
                df.columns = [c.strip() for c in df.columns]

                # Rename standard columns
                rename_map = {k: v for k, v in MCX_GOLD_STANDARD_COLS.items()
                              if k in df.columns}
                df = df.rename(columns=rename_map)

                # Parse trade date
                date_col = "trade_date" if "trade_date" in df.columns else df.columns[0]
                df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce")
                df = df.dropna(subset=[date_col])
                df = df.rename(columns={date_col: "trade_date"})

                # Parse expiry date if present
                if "expiry_date" in df.columns:
                    df["expiry_date"] = pd.to_datetime(
                        df["expiry_date"], dayfirst=True, errors="coerce"
                    )
                else:
                    df["expiry_date"] = pd.NaT

                df["contract_symbol"] = contract_symbol
                df["source"] = "MCX"

                for col in ["open", "high", "low", "close", "volume",
                            "open_interest", "turnover"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")

                frames.append(df)
            except Exception as e:
                self.logger.warning(f"Skipping {f.name}: {e}")

        if not frames:
            raise ValueError("No valid MCX gold contract frames loaded.")

        result = pd.concat(frames, ignore_index=True)
        result = result.sort_values(["trade_date", "contract_symbol"])

        # EXPLICITLY NOTE: No roll applied. This is raw per-contract data.
        result["roll_applied"] = False
        result["continuous_series"] = False

        return result

    @staticmethod
    def document_roll_methodology() -> str:
        """Return a description of the roll methodology decision space.

        The ACTUAL roll methodology must be chosen after the coverage audit.
        This method documents the options for researcher review.
        """
        return """
MCX Gold Futures Roll Methodology (NOT YET DECIDED)
====================================================
Status: PENDING — to be decided after coverage audit

Options under consideration:
  1. Front-month roll (N days before expiry)
     - Simple, transparent
     - N must be chosen to avoid delivery risk
     - Standard N values: 5, 10, or 15 trading days before expiry
     
  2. Open-interest weighted roll
     - Switch when next contract's OI exceeds front month OI
     - Empirically tracks where market liquidity is concentrated
     - Requires OI data (preserved in raw data)
     
  3. Panama canal method
     - Adjusts historical prices to eliminate price gaps at roll
     - Backward-adjusting, deterministic
     - Introduces non-zero base effect
     
  4. Percentage-adjustment roll
     - Similar to Panama but percentage-based
     - Avoids large absolute adjustments

LOOK-AHEAD REQUIREMENT:
  Any roll methodology must be implemented such that:
  - The roll decision on day T uses only data available at end-of-day T
  - No future contract's price is used in the roll decision before it is traded
  - The roll look-up table must be reconstructed without future knowledge

Decision: To be recorded here after coverage audit and researcher review.
"""
