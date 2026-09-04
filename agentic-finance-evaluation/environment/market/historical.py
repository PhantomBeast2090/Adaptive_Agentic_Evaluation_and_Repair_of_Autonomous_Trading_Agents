import hashlib
from typing import Any, Dict, Optional, Tuple

import pandas as pd


class HistoricalMarket:
    """Deterministic replay of a SPY/^VIX parquet split.

    An optional inclusive `[start_date, end_date]` window selects a contiguous
    slice of the split. Windowing is what makes distinct static scenarios
    possible from a single split file without mutating or duplicating data.
    """

    def __init__(
        self,
        data_path: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ):
        self.data_path = data_path
        self.requested_start_date = start_date
        self.requested_end_date = end_date

        self.df = pd.read_parquet(data_path)
        self._validate_data()

        if start_date is not None or end_date is not None:
            self.df = self._slice_window(self.df, start_date, end_date)

        self.dates = self.df.index.tolist()
        self.current_step = 0
        self.max_steps = len(self.df) - 1

    @property
    def window_start_date(self) -> str:
        return self.dates[0].strftime("%Y-%m-%d")

    @property
    def window_end_date(self) -> str:
        return self.dates[-1].strftime("%Y-%m-%d")

    def reset(self) -> Dict[str, Any]:
        self.current_step = 0
        return self._get_obs()

    def step(self) -> Tuple[Optional[Dict[str, Any]], bool]:
        if self.current_step >= self.max_steps:
            return None, True  # Done
        self.current_step += 1
        return self._get_obs(), False

    def _get_obs(self) -> Dict[str, Any]:
        row = self.df.iloc[self.current_step]
        date = self.dates[self.current_step]

        market_price = float(row.get("SPY", 0.0))
        vix = float(row.get("^VIX", 0.0))

        return {
            "date": date.strftime("%Y-%m-%d"),
            "market_price": market_price,
            "vix": vix,
        }

    def fingerprint(self) -> str:
        """Stable SHA-256 digest of the replayed window.

        Recorded with every episode so a result can be traced to the exact
        market rows that produced it, independently of the file path.
        """
        canonical = "\n".join(
            f"{date.strftime('%Y-%m-%d')},{float(spy)!r},{float(vix)!r}"
            for date, spy, vix in zip(self.dates, self.df["SPY"], self.df["^VIX"])
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _slice_window(
        self,
        df: pd.DataFrame,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> pd.DataFrame:
        start = pd.Timestamp(start_date) if start_date is not None else None
        end = pd.Timestamp(end_date) if end_date is not None else None

        if start is not None and end is not None and start > end:
            raise ValueError(
                f"start_date {start_date} must not be after end_date {end_date}"
            )

        window = df.loc[start:end]
        if window.empty:
            raise ValueError(
                f"Market window [{start_date}, {end_date}] selects no rows from {self.data_path}"
            )
        return window

    def _validate_data(self) -> None:
        required_columns = {"SPY", "^VIX"}
        missing_columns = required_columns.difference(self.df.columns)
        if missing_columns:
            raise ValueError(f"Market data missing required columns: {sorted(missing_columns)}")
        if self.df.empty:
            raise ValueError("Market data must contain at least one row")
        if self.df.index.has_duplicates:
            raise ValueError("Market data index contains duplicate timestamps")
        if not self.df.index.is_monotonic_increasing:
            raise ValueError("Market data index must be sorted in ascending order")
        if self.df[["SPY", "^VIX"]].isna().any().any():
            raise ValueError("Market data contains missing SPY or ^VIX values")
        if (self.df[["SPY", "^VIX"]] <= 0).any().any():
            raise ValueError("Market data contains non-positive SPY or ^VIX values")
